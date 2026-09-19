#!/usr/bin/env python3
"""Macau: nationality and usual language from the 2021 Population Census.

Macau is one first-level shape on this map, drawn under China, and its
census is not China's: the Statistics and Census Service (DSEC) counts the
Special Administrative Region every ten years, with a by-census between,
and asks nationality, ethnicity and usual language, which the mainland
census does not. Religion it does not ask, in either round: the 147 pages
of the 2021 *Detailed Results* and the 133 of the 2016 By-census mention
religion on no page at all (measured by the runner's probe, terms
religion/religious/Buddhis/Catholic, zero pages each), so the shape's
religion stays declared not collected under the China policy.

The source is the *Detailed Results of 2021 Population Census* (revised
version, October 2022), which DSEC publishes as one PDF. Two of its
statistical tables are read, both sexes, the Total row:

* **Table 6** -- *Population by gender, age group and nationality*:
  Chinese, Filipino, Other Asian countries, Portuguese, Others, over the
  total population of 682,070. This is carried as the ethnicity field with
  ``ethnicity_basis`` "nationality", because it is a passport and not an
  ancestry. The census's own ethnicity table (Table 7) is not the better
  answer: it distinguishes Chinese, Portuguese and the mixed
  Chinese-Portuguese but folds every other people -- the Filipinos, the
  Vietnamese, everyone -- into one "Others" of 57,688, where the
  nationality table names the Filipinos. The report's text puts the
  Vietnamese at 1.8% of the population, inside "Other Asian countries";
  the table does not print them apart.
* **Table 10** -- *Population by gender, age group and usual language*:
  Cantonese, Mandarin, Other Chinese dialects, Portuguese, English,
  Tagalog, Others, over the 663,782 people aged 3 and over. Usual
  language is the language a person mostly uses at home, one per person;
  ``language_basis`` says the universe.

The PDF sets each table's figures with a space for the thousands separator
and a text reader runs a row together as ``682 070 608 379 33 896 ...``,
so a row is not a list of numbers until it is cut into as many figures as
the table has columns. Every cut is tried, and the one kept is the one in
which the Total column equals the sum of the others -- the table's own
arithmetic decides where the figures begin and end, and a row with no such
cut, or more than one, is refused.

Every figure is checked before anything is written: the Total row of each
table must equal the census's published population (682,070 and 663,782,
the figures its text and its principal-characteristics table state); the
language counts must agree with the same table as the report prints it a
second time under *Principal Characteristics of Population* (page 40),
count for count, and its printed shares with the shares computed here;
and each composition must sum to 100 within three tenths. A share the
report's text states in prose (Chinese nationality 89.2%, Cantonese
81.0%) is held against the result too; a disagreement there is written
into the note in one sentence rather than refused.

Usage:
    python -m scripts.fetch_census.macau_census
    python -m scripts.fetch_census.macau_census --text dump.txt   # a saved probe_pdf dump
"""

from __future__ import annotations

import argparse
import io
import re
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from ._shared import PROCESSED, log, measure, record, shares, write_json

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from probe_pdf import PAGE_BREAK, fetch_blob  # noqa: E402

OUT = "macau_census.json"
YEAR = 2021
NAME = "Macau Special Administrative Region"
URL = ("https://www.dsec.gov.mo/getAttachment/6cb29f2f-524a-488f-aed3-4d7207bb109e/"
       "E_CEN_PUB_2021_Y.aspx")
PAGE = "https://www.dsec.gov.mo/en-US/Statistic?id=103"
SOURCE = ("Statistics and Census Service (DSEC), Macao SAR, Detailed Results of 2021 "
          "Population Census (revised version, October 2022)")
LICENCE = ("DSEC official statistics; reproduction of the data is allowed provided "
           "the source is quoted")
ETHNICITY_BASIS = "nationality"
LANGUAGE_BASIS = "usual language, population aged 3 and over"
TOLERANCE = 0.3
SHARE_TOLERANCE = 0.1

# The census's published populations, which the tables' Total rows must
# reproduce: the total population (section 1.1 of the report) and the
# population aged 3 and above (Principal Characteristics, page 40).
TOTAL_POPULATION = 682_070
POPULATION_AGED_3_AND_OVER = 663_782

# The two tables, by their titles, and their columns after Total in the
# order printed. They are pages 66 and 70 of the October 2022 revision (the
# principal-characteristics page is 40), found by title within this window
# rather than assumed.
NATIONALITY_TITLE = "POPULATION BY GENDER, AGE GROUP AND NATIONALITY"
LANGUAGE_TITLE = "POPULATION BY GENDER, AGE GROUP AND USUAL LANGUAGE"
NATIONALITY_COLUMNS = ["Chinese", "Filipino", "Other Asian countries", "Portuguese", "Others"]
LANGUAGE_COLUMNS = ["Cantonese", "Mandarin", "Other Chinese dialects", "Portuguese",
                    "English", "Tagalog", "Others"]
# The principal-characteristics page, which prints the language table again
# with a share beside each count, is known by these three marks together.
PRINCIPAL_MARKS = ("Population aged 3 and above", "Usual language", "Structure (%)")
PAGE_WINDOW = (36, 80)

# The census's labels to the map's words. "Other Asian countries" is a
# nationality, and is placed as one in scripts/group_tree.py.
ETHNICITY_LABELS = {"Other Asian countries": "Other Asian nationality",
                    "Others": "Other nationalities"}
LANGUAGE_LABELS = {"Others": "Other languages"}
# The principal-characteristics page prints two rows that are sums of Table
# 10's columns: "Chinese" over the three Chinese languages, and "Other" over
# Tagalog and Others together.
PRINCIPAL_SUMS = {"Chinese": ("Cantonese", "Mandarin", "Other Chinese dialects"),
                  "Other": ("Tagalog", "Others")}

# What the report's text states in prose (sections 1.4 and 1.7), held
# against the tables as a soft check: a disagreement goes into the note.
STATED = {
    "ethnicity": {"Chinese": 89.2, "Portuguese": 1.3, "Filipino": 5.0},
    "language": {"Cantonese": 81.0, "Mandarin": 4.7, "Other Chinese dialects": 5.4,
                 "Portuguese": 0.6, "English": 3.6},
}

GROUP = re.compile(r"\d{1,3}")
THOUSANDS = re.compile(r"\d{3}")
PRINCIPAL_ROW = re.compile(r"^([A-Za-z][A-Za-z /-]*?)\s+(\d{1,3}(?: \d{3})*)\s+(\d+\.\d)\b")


def readings(tokens: list[str], n: int) -> list[list[int]]:
    """Every way of reading ``tokens`` as ``n`` figures set with spaced thousands.

    A figure is a first group of one to three digits followed by any number
    of three-digit groups. "682 070 608 379" read as two figures is 682,070
    and 608,379 -- or 682 and 070,608,379, or 682,070,608 and 379 -- and
    nothing in the text says which, so all of them are returned and the
    caller chooses by the table's arithmetic.
    """
    def rec(i: int, left: int) -> list[list[int]]:
        if left == 0:
            return [[]] if i == len(tokens) else []
        if i >= len(tokens) or not GROUP.fullmatch(tokens[i]):
            return []
        out: list[list[int]] = []
        value, j = tokens[i], i + 1
        while True:
            out.extend([int(value), *rest] for rest in rec(j, left - 1))
            if j < len(tokens) and THOUSANDS.fullmatch(tokens[j]):
                value, j = value + tokens[j], j + 1
            else:
                break
        return out
    return rec(0, n)


def total_row(page: str, columns: list[str], what: str) -> tuple[int, dict[str, int]]:
    """(Total, {column: count}) from the first both-sexes row of a table page.

    The row is the "MF" line under the title, its figures run together by
    the text reader; the one cut in which Total equals the sum of the
    columns is the reading, and a page with no such cut, or two, is refused.
    """
    flat = re.sub(r"\s+", " ", page)
    for column in columns:
        if column not in flat:
            raise SystemExit(f"macau_census: the {what} page has no column {column!r}")
    for line in page.splitlines():
        if not line.startswith("MF "):
            continue
        tokens = line.split()[1:]
        found = [r for r in readings(tokens, len(columns) + 1) if r[0] == sum(r[1:])]
        if len(found) != 1:
            raise SystemExit(f"macau_census: the {what} Total row {line!r} has "
                             f"{len(found)} readings in which Total is the sum of "
                             f"the {len(columns)} columns")
        total, *figures = found[0]
        return total, dict(zip(columns, figures))
    raise SystemExit(f"macau_census: no both-sexes (MF) row on the {what} page")


def principal_language(page: str) -> dict[str, tuple[int, float]]:
    """{label: (2021 count, printed 2021 share)} from the Usual language block."""
    lines = [line.strip() for line in page.splitlines()]
    try:
        start = lines.index("Usual language")
    except ValueError:
        raise SystemExit("macau_census: the principal-characteristics page has no "
                         "'Usual language' block") from None
    out: dict[str, tuple[int, float]] = {}
    for line in lines[start + 1:]:
        if line.startswith("Population aged"):
            break
        m = PRINCIPAL_ROW.match(line)
        if not m:
            raise SystemExit(f"macau_census: unreadable principal-characteristics "
                             f"row {line!r}")
        out[m.group(1).strip()] = (int(m.group(2).replace(" ", "")), float(m.group(3)))
    if not out:
        raise SystemExit("macau_census: the 'Usual language' block is empty")
    return out


def checked(field: str, counts: dict[str, int], total: int, published: int,
            stated: dict[str, float], caveats: list[str]) -> list[dict[str, Any]]:
    """Shares from the counts, refused unless they are the published population.

    The table's Total must be the population the census publishes, and the
    shares must sum to 100. A share the report's prose states differently
    is not a refusal: it is written down, in ``caveats``, for the note.
    """
    if total != published:
        raise SystemExit(f"macau_census: the {field} table totals {total:,} against "
                         f"the census's published {published:,}")
    rows = shares(counts, total=total)
    summed = sum(r["pct"] for r in rows)
    if abs(summed - 100.0) > TOLERANCE:
        raise SystemExit(f"macau_census: {field} shares sum to {summed:.1f}, not 100")
    by_name = {r["group"]: r["pct"] for r in rows}
    off = [f"{name} {by_name[name]}% here against {pct}% in the report's text"
           for name, pct in stated.items()
           if abs(by_name.get(name, 0.0) - pct) > SHARE_TOLERANCE]
    if off:
        caveats.append("The report's own text differs a little: " + "; ".join(off) + ".")
    return rows


def cross_check(counts: dict[str, int], total: int, principal: dict[str, tuple[int, float]],
                caveats: list[str]) -> None:
    """Table 10 against the same figures on the principal-characteristics page.

    Every count must agree exactly -- a column of Table 10 with its own row
    there, and the page's "Chinese" and "Other" rows with the columns they
    sum -- and each printed share must be the share computed here within a
    tenth; a share that is not goes into the note.
    """
    summed = {row: sum(counts[c] for c in parts) for row, parts in PRINCIPAL_SUMS.items()}
    direct = {label: count for label, count in counts.items()
              if not any(label in parts for parts in PRINCIPAL_SUMS.values())}
    off = []
    for label, count in {**direct, **summed}.items():
        if label not in principal:
            raise SystemExit(f"macau_census: the principal-characteristics page has no "
                             f"row {label!r}")
        printed_count, printed_share = principal[label]
        if printed_count != count:
            raise SystemExit(f"macau_census: {label} is {count:,} from Table 10 and "
                             f"{printed_count:,} under Principal Characteristics")
        computed = round(100.0 * count / total, 1)
        if abs(computed - printed_share) > SHARE_TOLERANCE:
            off.append(f"{label} {computed}% against a printed {printed_share}%")
    if off:
        caveats.append("The report prints slightly different shares beside the same "
                       "counts: " + "; ".join(off) + ".")


def locate(pages: Iterable[tuple[int, str]]) -> dict[str, str]:
    """The three pages read, found by their titles, from a stream of pages."""
    found: dict[str, str] = {}
    for number, text in pages:
        flat = re.sub(r"\s+", " ", text)
        if "nationality" not in found and NATIONALITY_TITLE in flat:
            found["nationality"] = text
            log(f"  Table 6 (nationality): page {number}")
        elif "language" not in found and LANGUAGE_TITLE in flat:
            found["language"] = text
            log(f"  Table 10 (usual language): page {number}")
        elif "principal" not in found and all(mark in flat for mark in PRINCIPAL_MARKS):
            found["principal"] = text
            log(f"  Principal Characteristics, usual language: page {number}")
        if len(found) == 3:
            break
    missing = {"nationality", "language", "principal"} - set(found)
    if missing:
        raise SystemExit(f"macau_census: no page carries {', '.join(sorted(missing))}")
    return found


def page_texts(blob: bytes, window: tuple[int, int] = PAGE_WINDOW
               ) -> Iterable[tuple[int, str]]:
    """(page number, text) for the pages in the window, extracted as needed.

    Only the pages asked for are read: extracting all 147 costs the runner
    most of an hour, and the tables sit in the report's middle.
    """
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(blob))
    log(f"  {len(reader.pages)} pages; reading {window[0]}-{window[1]}")
    for number in range(window[0], min(window[1], len(reader.pages)) + 1):
        yield number, reader.pages[number - 1].extract_text() or ""


def build(pages: dict[str, str]) -> list[dict[str, Any]]:
    from common import slugify

    total, counts = total_row(pages["nationality"], NATIONALITY_COLUMNS, "nationality")
    counts = {ETHNICITY_LABELS.get(k, k): v for k, v in counts.items()}
    ethnicity_caveats: list[str] = []
    ethnicity = checked("ethnicity", counts, total, TOTAL_POPULATION,
                        STATED["ethnicity"], ethnicity_caveats)

    total, counts = total_row(pages["language"], LANGUAGE_COLUMNS, "usual language")
    language_caveats: list[str] = []
    cross_check(counts, total, principal_language(pages["principal"]), language_caveats)
    counts = {LANGUAGE_LABELS.get(k, k): v for k, v in counts.items()}
    language = checked("language", counts, total, POPULATION_AGED_3_AND_OVER,
                       STATED["language"], language_caveats)

    log(f"  nationality: {len(ethnicity)} groups over {TOTAL_POPULATION:,} people; "
        f"usual language: {len(language)} over {POPULATION_AGED_3_AND_OVER:,} aged 3 "
        f"and over")
    for caveat in ethnicity_caveats + language_caveats:
        log(f"  note: {caveat}")
    sources = [
        {"field": "ethnicity", "name": f"{SOURCE}, Table 6", "url": URL, "license": LICENCE},
        {"field": "language", "name": f"{SOURCE}, Table 10", "url": URL, "license": LICENCE},
        {"field": "population", "name": f"{SOURCE}, Table 6", "url": URL, "license": LICENCE},
    ]
    return [record(
        f"CHN-{slugify(NAME)}", NAME, level="admin1", parent="CHN", country="CHN",
        aliases=["Macau", "Macao", "Macau SAR", "Macao SAR", "澳門"],
        sources=sources,
        population=measure(TOTAL_POPULATION, year=YEAR, source=SOURCE),
        ethnicity=ethnicity, ethnicity_year=YEAR, ethnicity_basis=ETHNICITY_BASIS,
        ethnicity_note=" ".join([
            f"{SOURCE}, Table 6: population by nationality, both sexes, of the "
            f"{TOTAL_POPULATION:,} people counted in August 2021.",
            "Nationality, not ethnicity: the census's ethnicity table (Table 7) folds "
            "every people but the Chinese and Portuguese into one 'Others', so the "
            "nationality table, which names the Filipinos, is carried and labelled "
            "for what it is.",
            "'Other Asian nationality' is the census's 'Other Asian countries', within "
            "which its text puts Vietnamese nationals at 1.8% of the population.",
            *ethnicity_caveats]),
        language=language, language_year=YEAR, language_basis=LANGUAGE_BASIS,
        language_note=" ".join([
            f"{SOURCE}, Table 10: usual language, both sexes, of the "
            f"{POPULATION_AGED_3_AND_OVER:,} people aged 3 and over.",
            "Usual language is the one language a person mostly uses at home; "
            "'Other languages' is the census's 'Others'.",
            *language_caveats]),
    )]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--text", default=None,
                    help="a saved probe_pdf dump of the report instead of the PDF")
    args = ap.parse_args()
    log(f"macau_census: {SOURCE}")
    if args.text:
        text = Path(args.text).read_text(encoding="utf-8")
        pages = enumerate(text.split(PAGE_BREAK), 1)
    else:
        pages = page_texts(fetch_blob(URL))
    records = build(locate(pages))
    write_json(PROCESSED / OUT, records)
    log(f"  wrote {len(records)} record to {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
