#!/usr/bin/env python3
"""Marshall Islands, 2021 Census: every atoll's people, age, sex, religion and ethnicity.

Two publications of the Economic Policy, Planning and Statistics Office
(EPPSO), both PDFs on ``rmieppso.org``:

* **RMI 2021 Census Report, Volume 1: Basic tables and administrative
  report** (86 pp). Table 3 is the population by atoll and sex; Table 9
  religion and Table 10 ethnicity by atoll, both of the 41,575 people in
  private households (Table 7 puts the other 843 in institutions -- the
  boarding high schools of Jaluit and Wotje, Majuro's and Kwajalein's).
* **RMI 2021 Census Analytical Report** (108 pp). Table 2.4 gives every
  atoll's median age and sex ratio, in whole numbers; Table 3.3 the share of
  people aged five and over who speak Marshallese and who speak another
  language, for Majuro, Kwajalein and the rural atolls taken together.

**What the map draws.** The boundary file draws 22 atolls, at both of its
levels, and the census counts 25: Bikini and Rongelap had nobody on census
night, and Lib (156 people) has no polygon. Each drawn atoll gets the same
record at both levels.

**Language.** The census asked which languages each person speaks, more than
one allowed, and published the answer for Majuro and Kwajalein but not for
any other atoll, so those two carry it and the rest say why they do not.

**Checks**, each refusing the run: the atolls of Table 3 add up to the
42,418 the census counted and every row's sexes to its total; Tables 9 and 10
add up across every row and their totals are Table 7's private-household
counts; Table 2.4 counts every atoll as Table 3 does and its sex ratio is
Table 3's, rounded; the Marshallese and other-language shares are read for
both atolls.

Usage:
    python -m scripts.fetch_census.marshall_census
"""

from __future__ import annotations

import argparse
import io
import re
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, gap, http_get, log, measure, write_json
from .oceania_common import (
    bind_level, check, load_units, population, sex_ratio, shares_of, summarise, unit_record,
)

OUT = "marshall_census.json"
YEAR = 2021
OFFICE = "Economic Policy, Planning and Statistics Office (EPPSO), Republic of the Marshall Islands"
TABLES_URL = ("https://rmieppso.org/download/8/census-surveys/1236/"
              "rmi-2021-census-table-report.pdf")
REPORT_URL = ("https://rmieppso.org/download/8/census-surveys/1234/"
              "marshall_islands_census_report_2021.pdf")
TABLES = f"{OFFICE}, RMI 2021 Census Report, Volume 1: Basic tables and administrative report"
REPORT = f"{OFFICE}, RMI 2021 Census Analytical Report"
LICENCE = "None stated -- EPPSO publication, cited as such"

NATIONAL = 42_418
PRIVATE = 41_575
# The census's atolls in its own order; the three the map does not draw.
ATOLLS = ("Ailinglaplap", "Ailuk", "Arno", "Aur", "Bikini", "Ebon", "Enewetak", "Jabat",
          "Jaluit", "Kili", "Kwajalein", "Lae", "Lib", "Likiep", "Majuro", "Maloelap", "Mejit",
          "Mili", "Namdrik", "Namu", "Rongelap", "Ujae", "Utirik", "Wotho", "Wotje")
UNDRAWN = {"Bikini", "Rongelap", "Lib"}
EMPTY = {"Bikini", "Rongelap"}

# Table 9's sixteen denominations and Table 10's sixteen ethnic groups, in the
# order the tables print them, under the names the map carries.
RELIGIONS = ("United Church of Christ", "Roman Catholic", "Assemblies of God",
             "Jehovah's Witnesses", "Reformed Congregational Church",
             "Church of Jesus Christ of Latter-day Saints", "Seventh-day Adventist",
             "Bukot Nan Jesus", "No religion", "Full Gospel", "Salvation Army",
             "Other religion", "Protestant Church", "New Beginning Church", "Baptist",
             "Batkan Light House Church")
RELIGION_HEADER = ("United", "Roman", "Assembly", "Jehovah", "Reformed", "Mormon", "Seventh",
                   "Bukot", "None", "Full", "Salvation", "Other", "Protes", "New", "Baptist",
                   "Batkan")
ETHNIC = ("Marshallese", "Micronesian (FSM)", "Palauan", "I-Kiribati", "Tuvaluan",
          "Taiwanese", "Chinese", "Japanese", "Korean", "Filipino", "American",
          "New Zealander", "Australian", "Fijian", "Other ethnicity", "Solomon Islander")
ETHNIC_HEADER = ("Marshall", "FSM", "Palau", "Kiribati", "Tuvalu", "Taiwan", "China", "Japan",
                 "Korea", "Philip", "USA", "Zealand", "Australia", "Fiji", "Other", "Solomon")
SPOKEN = ("Majuro", "Kwajalein")

NUMBER = re.compile(r"^\d{1,3}(?:,\d{3})*$")


def tokens(text: str) -> list[str]:
    """The figures of a row, with the pieces the PDF's kerning split put back.

    "1,14 0" is 1,140 and "57. 0" is 57.0: a piece that ends inside a group
    of thousands, or on a decimal point, is joined to the piece after it.
    """
    out: list[str] = []
    for piece in text.split():
        if out and (re.fullmatch(r"\d{1,3}(?:,\d{3})*,\d{1,2}", out[-1])
                    or out[-1].endswith(".")) and re.fullmatch(r"\d+", piece):
            out[-1] += piece
        else:
            out.append(piece)
    return out


def counts(text: str, width: int, where: str) -> list[int]:
    figures = tokens(text)
    check(len(figures) == width and all(NUMBER.match(f) for f in figures),
          f"marshall_census: {where}: {text!r} is not {width} counts")
    return [int(f.replace(",", "")) for f in figures]


def section(lines: list[str], start: str, stops: tuple[str, ...]) -> list[str]:
    """The lines from a table's title to the next table's."""
    # The contents pages list every title too, with dot leaders after it.
    at = next((i for i, ln in enumerate(lines) if ln.startswith(start) and "...." not in ln),
              None)
    check(at is not None, f"marshall_census: no {start!r}")
    end = next((i for i in range(at + 1, len(lines))
                if any(lines[i].startswith(s) for s in stops)), len(lines))
    return lines[at:end]


ROW = re.compile(r"^(\d{1,2})\s*[–-]\s*([A-Za-z]+)\s+(\d.*)$")


def atoll_rows(lines: list[str], width: int, table: str) -> dict[str, list[int]]:
    """{atoll: figures} from the numbered atoll rows of one table."""
    out: dict[str, list[int]] = {}
    for line in lines:
        match = ROW.match(line.strip())
        if not match or match.group(2) not in ATOLLS:
            continue
        name = match.group(2)
        check(name not in out, f"marshall_census: {table} has two rows for {name}")
        out[name] = counts(match.group(3), width, f"{table} {name}")
    check(set(out) == set(ATOLLS),
          f"marshall_census: {table} lacks {sorted(set(ATOLLS) - set(out))}")
    return out


def total_row(lines: list[str], width: int, table: str) -> list[int]:
    found = [counts(ln.strip()[len("Total"):], width, f"{table} total")
             for ln in lines if ln.strip().startswith("Total ")
             and re.search(r"\d", ln)]
    check(found and all(f == found[0] for f in found),
          f"marshall_census: {table}'s total rows disagree: {found}")
    return found[0]


def header_in_order(lines: list[str], words: tuple[str, ...], table: str) -> None:
    text = " ".join(lines[:40])
    at = 0
    for word in words:
        found = text.find(word, at)
        check(found >= 0, f"marshall_census: {table}'s header lacks {word!r} after "
                          f"position {at}")
        at = found + len(word)


def read_tables(pages: list[str]) -> dict[str, Any]:
    lines = [ln.strip() for page in pages for ln in page.splitlines() if ln.strip()]
    sex = section(lines, "Table 3.", ("Table 4.",))
    households = section(lines, "Table 7.", ("Table 8.",))
    faith = section(lines, "Table 9.", ("Table 10.",))
    ethnic = section(lines, "Table 10.", ("Table 11.", "Table 1 1."))

    people = atoll_rows(sex, 3, "Table 3")
    check(total_row(sex, 3, "Table 3")[0] == NATIONAL,
          f"marshall_census: Table 3 does not count {NATIONAL:,}")
    check(sum(p[0] for p in people.values()) == NATIONAL,
          "marshall_census: Table 3's atolls do not add up to the country")
    for name, (total, male, female) in people.items():
        check(male + female == total, f"marshall_census: {name}'s sexes do not make {total}")

    private = {name: row[3] for name, row in atoll_rows(households, 9, "Table 7").items()}
    check(sum(private.values()) == PRIVATE,
          f"marshall_census: Table 7's private households hold {sum(private.values()):,}")

    header_in_order(faith, RELIGION_HEADER, "Table 9")
    header_in_order(ethnic, ETHNIC_HEADER, "Table 10")
    out: dict[str, Any] = {"people": people, "private": private, "religion": {},
                           "ethnicity": {}}
    for field, block, labels in (("religion", faith, RELIGIONS),
                                 ("ethnicity", ethnic, ETHNIC)):
        rows = atoll_rows(block, 1 + len(labels), f"{field} table")
        for name, row in rows.items():
            check(sum(row[1:]) == row[0],
                  f"marshall_census: {name}'s {field} adds up to {sum(row[1:])}, not {row[0]}")
            check(row[0] == private[name],
                  f"marshall_census: {name}'s {field} counts {row[0]}, Table 7 {private[name]}")
            out[field][name] = dict(zip(labels, row[1:]))
    log(f"  Basic Tables: {len(people)} atolls adding to {NATIONAL:,}; religion and ethnicity "
        f"of the {PRIVATE:,} in private households")
    return out


AGE_ROW = re.compile(r"^([A-Za-z]+)\s+(\d.*)$")


def read_report(pages: list[str], people: dict[str, list[int]]) -> dict[str, Any]:
    lines = [ln.strip() for page in pages for ln in page.splitlines() if ln.strip()]
    ages = section(lines, "Table 2.4.", ("Over the years", "Table 2.5", "Figure 2.5"))
    medians: dict[str, tuple[int, int]] = {}
    for line in ages:
        match = AGE_ROW.match(line)
        if not match or match.group(1) not in ATOLLS:
            continue
        figures = tokens(match.group(2))
        check(len(figures) == 12, f"marshall_census: Table 2.4 row {line!r}")
        total = int(figures[6].replace(",", ""))
        name = match.group(1)
        check(total == people[name][0],
              f"marshall_census: Table 2.4 counts {name} at {total}, Table 3 at "
              f"{people[name][0]}")
        median, ratio = int(figures[10]), int(figures[11])
        computed = sex_ratio(people[name][1], people[name][2])
        check(abs(computed - ratio) <= 1,
              f"marshall_census: {name}'s printed sex ratio {ratio} is not Table 3's "
              f"{computed}")
        medians[name] = (median, ratio)
    missing = sorted(set(ATOLLS) - EMPTY - set(medians))
    check(not missing, f"marshall_census: Table 2.4 has no row for {missing}")

    spoken = section(lines, "Table 3.3.", ("Overall, percentages", "Table 3.4"))
    language: dict[str, dict[str, float]] = {}
    for i, line in enumerate(spoken):
        head = line.split()[0] if line.split() else ""
        if head not in SPOKEN or i + 2 >= len(spoken):
            continue
        shares = {}
        for row, label in ((spoken[i + 1], "Marshallese"), (spoken[i + 2], "Other languages")):
            prefix = ("Speaks Marshallese (%)" if label == "Marshallese"
                      else "Speaks other languages (%)")
            check(row.startswith(prefix), f"marshall_census: Table 3.3 under {head}: {row!r}")
            shares[label] = float(tokens(row[len(prefix):])[0])
        language[head] = shares
    check(set(language) == set(SPOKEN), f"marshall_census: Table 3.3 gave {sorted(language)}")
    log(f"  Analytical Report: medians for {len(medians)} atolls; languages for "
        f"{', '.join(sorted(language))}")
    return {"medians": medians, "language": language}


LANGUAGE_GAP = (
    "The 2021 census asked which languages each person speaks, and the office publishes "
    "the answer for Majuro, Kwajalein and the rural atolls taken together (Analytical "
    "Report, Table 3.3): 98.3% of rural people aged five and over speak Marshallese and "
    "11.5% another language. No atoll outside Majuro and Kwajalein has a figure of its own, "
    "and the Basic Tables have no language table.")
COMPOSITION_NOTE = ("{what}, 2021 Census (Basic Tables, Table {table}): shares of the "
                    "{private:,} people in this atoll's private households{rest}.")


def fields_for(name: str, tables: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    total, male, female = tables["people"][name]
    private = tables["private"][name]
    rest = (f"; the {total - private:,} counted in its institutions -- boarding schools, "
            f"hospitals, hostels -- are in neither table" if total > private else "")
    median, printed = report["medians"][name]
    fields: dict[str, Any] = {
        "population": population(total, YEAR, f"{TABLES} (Table 3)"),
        "sex_ratio": measure(sex_ratio(male, female), unit="males_per_100_females", year=YEAR,
                             source=f"{TABLES} (Table 3)"),
        "sex_ratio_note": (f"Males per 100 females, 2021 Census (Table 3); the Analytical "
                           f"Report prints {printed}."),
        "median_age": measure(median, unit="years", year=YEAR,
                              source=f"{REPORT} (Table 2.4)"),
        "median_age_note": ("Median age at the 2021 census, as the Analytical Report prints "
                            "it (Table 2.4), in whole years."),
        "religion": shares_of(tables["religion"][name], private),
        "religion_year": YEAR,
        "religion_note": COMPOSITION_NOTE.format(what="Religion", table=9, private=private,
                                                 rest=rest),
        "ethnicity": shares_of(tables["ethnicity"][name], private),
        "ethnicity_year": YEAR,
        "ethnicity_note": COMPOSITION_NOTE.format(what="Ethnicity", table=10, private=private,
                                                  rest=rest),
    }
    spoken = report["language"].get(name)
    if spoken:
        fields["language"] = [{"group": label, "pct": pct} for label, pct in spoken.items()]
        fields["language_year"] = YEAR
        fields["language_note"] = (
            f"Languages spoken by people aged five and over, more than one allowed, 2021 "
            f"Census (Analytical Report, Table 3.3): {spoken['Marshallese']}% speak "
            f"Marshallese and {spoken['Other languages']}% another language. The census does "
            f"not publish which other language.")
    else:
        fields["language"] = gap(NOT_AVAILABLE, LANGUAGE_GAP)
    return fields


SOURCES = [
    {"field": "population/sex_ratio/religion/ethnicity", "name": TABLES, "url": TABLES_URL,
     "year": YEAR, "license": LICENCE},
    {"field": "median_age/language", "name": REPORT, "url": REPORT_URL, "year": YEAR,
     "license": LICENCE},
]


def build(tables: dict[str, Any], report: dict[str, Any], admin1: list[dict[str, Any]],
          admin2: list[dict[str, Any]]) -> list[dict[str, Any]]:
    drawn = [a for a in ATOLLS if a not in UNDRAWN]
    records = []
    for level, units in (("admin1", admin1), ("admin2", admin2)):
        parents = {u["id"]: u["name"] for u in admin1} if level == "admin2" else {}
        bound = bind_level({a: (a, "") for a in drawn}, units, parents)
        for atoll, unit in bound.items():
            records.append(unit_record("MHL", atoll, unit["name"], unit, level, None, SOURCES,
                                       **fields_for(atoll, tables, report)))
    lib = tables["people"]["Lib"][0]
    log(f"  no polygon: Lib ({lib} people); Bikini and Rongelap counted nobody")
    return records


def pages_of(url: str) -> list[str]:
    from pypdf import PdfReader  # noqa: PLC0415
    blob = http_get(url, binary=True, timeout=600)
    check(isinstance(blob, bytes) and blob[:5] == b"%PDF-", f"marshall_census: {url} is no PDF")
    return [(page.extract_text() or "") for page in PdfReader(io.BytesIO(blob)).pages]


def main() -> int:
    argparse.ArgumentParser(description=__doc__,
                            formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    log("marshall_census: 2021 Census basic tables and analytical report")
    tables = read_tables(pages_of(TABLES_URL))
    report = read_report(pages_of(REPORT_URL), tables["people"])
    records = build(tables, report, load_units("MHL", "admin1"), load_units("MHL", "admin2"))
    log("  " + summarise(records))
    write_json(PROCESSED / OUT, records)
    log(f"  wrote {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
