#!/usr/bin/env python3
"""Antigua and Barbuda: the 2011 census by parish.

Two of the Statistics Division's own publications of the 2011 Population and
Housing Census:

* **Book of Statistical Tables I, Table 5.1**: the population of each parish
  by sex, institutional population included -- 85,567 in all. This gives the
  population and the sex ratio.
* **The census's REDATAM base** (``ATGPHC2011`` on CELADE's server), each
  person counted with the base's weight (WGHT, the Division's parish-specific
  correction for households it could not reach, Table D of the same book):
  age in single years (Q47), ethnic group (Q48) and religion (Q49) by parish.
  The weighted base holds 84,816 people, the household population; the Book
  publishes ethnicity and religion for the whole country only.

The base and the book split Saint John's into the City and the rest of the
parish; the map draws one Saint John, so the two are summed. Redonda, which
no one lives on, is in neither.

Checks, each of which stops the run: Table 5.1's parishes make its total by
sex and both; every weighted table's rows make its parish's total within the
rounding its weights leave, and each parish's ethnic groups and ages make its
sexes, its religions and those not asked the question too; the weighted
parishes stand within 3% of Table 5.1's.

The 2011 person questionnaire asks no language question (its eight pages ask
ethnic group and religion, and nothing on language).

Usage:
    python -m scripts.fetch_census.antigua_census
"""

from __future__ import annotations

import argparse
import io
import json
import re
from collections import Counter, defaultdict
from typing import Any

from ._shared import (NOT_AVAILABLE, PROCESSED, gap, http_get, log, measure, record, shares,
                      write_json)
from .binding import fold
from .redatam import Server, median_age, tables

OUT = PROCESSED / "antigua_census.json"
SITE = PROCESSED.parent.parent / "site" / "data"
CMDSET = "https://prod.redatam.org/binatg/RpWebStats.exe/CmdSet"
PORTAL = "https://prod.redatam.org/binatg/RpWebEngine.exe/Portal?BASE=ATGPHC2011&lang=ENG"
BOOK = ("https://statistics.gov.ag/wp-content/uploads/2017/10/"
        "Census-2011-Book-of-Statistical-Tables-I.pdf")
SOURCE_BOOK = ("Statistics Division of Antigua and Barbuda, 2011 Population and Housing "
               "Census, Book of Statistical Tables I, Table 5.1: Population by Parish by "
               "Census Year by Sex")
SOURCE_BASE = ("Statistics Division of Antigua and Barbuda, 2011 Population and Housing "
               "Census, REDATAM base ATGPHC2011 (weighted)")
YEAR = 2011
TOTAL = 85_567
QUESTIONNAIRE = ("https://statistics.gov.ag/wp-content/uploads/2017/12/"
                 "Antigua-and-Barbuda-2011-Census-Person-Questionnaire-Sample.pdf")
LANGUAGE_GAP = ("Antigua and Barbuda's 2011 census asks no language question: the person "
                f"questionnaire ({QUESTIONNAIRE}) asks ethnic group and religion and nothing "
                "on language, and the REDATAM base holds no language variable.")
# The map's parish -> the book's and the base's names for it.
PARISHES = {
    "Saint John": (("St. John City", "St. John Rural"),
                   ("Saint John's (City)", "Saint John (Rural)")),
    "Saint George": (("St. George",), ("Saint George",)),
    "Saint Peter": (("St. Peter",), ("Saint Peter",)),
    "Saint Philip": (("St. Philip",), ("Saint Philip",)),
    "Saint Paul": (("St. Paul",), ("Saint Paul",)),
    "Saint Mary": (("St. Mary",), ("Saint Mary",)),
    "Barbuda": (("Barbuda",), ("Barbuda",)),
}
ETHNICITY = {
    "African descendent": "African descent", "Caucasian/White": "White",
    "East Indian/India": "East Indian", "Mixed (Black/White)": "Mixed (Black and White)",
    "Mixed (Other)": "Mixed (other)", "Hispanic": "Hispanic",
    "Syrian/Lebanese": "Syrian/Lebanese", "Other": "Other",
    "Don't know/Not stated": "Not stated",
}
RELIGION = {
    "Adventist": "Seventh-day Adventist", "Anglican": "Anglican", "Baptist": "Baptist",
    "Church of God": "Church of God", "Evangelical": "Evangelical",
    "Jehovah Witness": "Jehovah's Witnesses", "Methodist": "Methodist",
    "Moravian": "Moravian", "Nazarene": "Church of the Nazarene",
    "None/no religion": "No religion", "Pentecostal": "Pentecostal",
    "Rastafarian": "Rastafarian", "Roman Catholic": "Roman Catholic",
    "Weslyan Holiness": "Wesleyan Holiness Church", "Other": "Other religion",
    "Don't know/Not stated": "Not stated",
}
NUMBER = re.compile(r"^(?:\d{1,3}(?:,\d{3})*|\d+)$")


def present(counts: dict[str, float]) -> list[dict]:
    """Shares of the categories anyone is counted in."""
    return shares({k: v for k, v in counts.items() if v})


def near(made: float, printed: float, what: str, slack: float) -> None:
    if abs(made - printed) > slack:
        raise SystemExit(f"antigua_census: {what} make {made:,}, printed {printed:,}")


# -- the book -------------------------------------------------------------------------

def table_5_1(lines: list[str]) -> dict[str, tuple[int, int, int]]:
    """{book parish: (total, men, women) in 2011} from Table 5.1, after its checks."""
    out: dict[str, tuple[int, int, int]] = {}
    for line in lines:
        if line.startswith("Institutional population") or line.startswith("Table 5.2"):
            break
        tokens = line.split()
        if len(tokens) > 6 and all(NUMBER.match(t) for t in tokens[-6:]):
            total, men, women = (int(t.replace(",", "")) for t in tokens[-3:])
            label = " ".join(tokens[:-6])
            if men + women != total:
                raise SystemExit(f"antigua_census: Table 5.1's {label}: {men:,} men and "
                                 f"{women:,} women make no {total:,}")
            out[label] = (total, men, women)
    whole = out.pop("Total", None)
    if whole is None or whole[0] != TOTAL:
        raise SystemExit(f"antigua_census: Table 5.1's total is {whole}")
    for i, what in enumerate(("people", "men", "women")):
        if sum(v[i] for v in out.values()) != whole[i]:
            raise SystemExit(f"antigua_census: Table 5.1's parishes do not make its {what}")
    known = {name for book, _ in PARISHES.values() for name in book}
    if set(out) != known:
        raise SystemExit(f"antigua_census: Table 5.1 has {sorted(out)}, not {sorted(known)}")
    return out


def book_lines() -> list[str]:
    import pdfplumber
    with pdfplumber.open(io.BytesIO(http_get(BOOK, binary=True, cache=False))) as pdf:
        for page in pdf.pages:
            lines = (page.extract_text() or "").splitlines()
            start = next((i for i, l in enumerate(lines)
                          if l.startswith("Table 5.1: Population by Parish")
                          and not re.search(r"\.{4,}", l)), None)
            if start is not None:
                return lines[start + 1:]
    raise SystemExit("antigua_census: the book has no Table 5.1")


# -- the base --------------------------------------------------------------------------

def by_parish(found: list[dict], what: str) -> dict[str, dict[str, Any]]:
    """{base area name: {"rows": Counter, "total", "na"}} from one weighted variable."""
    out = {}
    for table in found:
        if not table["area"]:
            continue
        rows, na = Counter(), table["na"] or 0
        for label, n in table["rows"]:
            # The English server writes "NotApp : 101" where the Spanish writes
            # "No Aplica": those the question was not put to, not a category.
            if re.match(r"^(?:NotApp|Missing)\b", label):
                na += n
            else:
                rows[label] += n
        near(sum(rows.values()), table["total"], f"the base's {what} in {table['name']}",
             slack=len(rows))
        out[table["name"]] = {"rows": rows, "total": table["total"], "na": na}
    known = {name for _, base in PARISHES.values() for name in base}
    if set(out) != known:
        raise SystemExit(f"antigua_census: the base's {what} has {sorted(out)}")
    return out


def read_base() -> dict[str, dict[str, dict[str, Any]]]:
    server = Server(CMDSET, "ATGPHC2011", lang="eng", who="antigua_census")
    asked = [("sex", "PERSON.Q45_SEX"), ("age", "PERSON.Q47_AGE"),
             ("ethnicity", "PERSON.Q48_ETHNIC"), ("religion", "PERSON.Q49_RELIGION")]
    lines = ["RUNDEF Job", "    SELECTION ALL", ""]
    for i, (_, variable) in enumerate(asked, 1):
        lines += [f"TABLE T{i}", "    AS FREQUENCY", f"    OF {variable}",
                  "    AREABREAK PARISH", "    WEIGHT PERSON.WGHT", ""]
    pages = server.output("\n".join(lines))
    if len(pages) != len(asked):
        raise SystemExit(f"antigua_census: {len(asked)} tables asked, {len(pages)} came back")
    out = {what: by_parish(tables(page, "Counts"), what) for (what, _), page in zip(asked, pages)}
    for area, sex in out["sex"].items():
        for what in ("age", "ethnicity"):
            near(out[what][area]["total"] + out[what][area]["na"], sex["total"],
                 f"the base's {what} in {area} against its sexes", slack=3)
        religion = out["religion"][area]
        near(religion["total"] + religion["na"], sex["total"],
             f"the base's religions and those not asked in {area} against its sexes", slack=3)
    return out


def ages(rows: Counter) -> tuple[Counter, int]:
    """(Counter(age: people), people of unstated age) from the base's single years."""
    known, unstated = Counter(), 0
    for label, n in rows.items():
        m = re.match(r"^(\d+)", label.strip())
        if m and int(m[1]) < 120:
            known[int(m[1])] += n
        else:
            unstated += n
    return known, unstated


def mapped(rows: Counter, labels: dict[str, str], what: str) -> dict[str, float]:
    out: dict[str, float] = defaultdict(float)
    for label, n in rows.items():
        if label not in labels:
            raise SystemExit(f"antigua_census: {what} {label!r} is not one this reads")
        out[labels[label]] += n
    return dict(out)


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    book = table_5_1(book_lines())
    base = read_base()
    admin1 = json.loads((SITE / "admin1" / "ATG.units.json").read_text())
    shapes = {fold(u["name"]): u for u in admin1}
    records = []
    for parish, (book_names, base_names) in PARISHES.items():
        shape = shapes.get(fold(parish))
        if shape is None:
            raise SystemExit(f"antigua_census: {parish} has no polygon")
        total = sum(book[n][0] for n in book_names)
        men = sum(book[n][1] for n in book_names)
        women = sum(book[n][2] for n in book_names)
        weighted = sum(base["sex"][n]["total"] for n in base_names)
        if abs(weighted - total) > 0.03 * total:
            raise SystemExit(f"antigua_census: the base holds {weighted:,} in {parish}, "
                             f"Table 5.1 {total:,}")
        years, unstated = Counter(), 0
        ethnic: Counter = Counter()
        religion: Counter = Counter()
        for n in base_names:
            known, missing = ages(base["age"][n]["rows"])
            years.update(known)
            unstated += missing
            ethnic.update(mapped(base["ethnicity"][n]["rows"], ETHNICITY, "ethnic group"))
            religion.update(mapped(base["religion"][n]["rows"], RELIGION, "religion"))
        not_asked = sum(base["religion"][n]["na"] for n in base_names)
        log(f"  {parish}: Table 5.1 {total:,}, the weighted base {weighted:,}; "
            f"{unstated:,} of unstated age; {not_asked:,} not asked their religion")
        records.append(record(
            f"ATG-SD-{fold(parish)}", shape["name"], level="admin1", parent="ATG",
            country="ATG", match_by="shape_id", shape_id=shape["id"],
            population=measure(total, year=YEAR, source=SOURCE_BOOK),
            population_note=("The 2011 census's population of the parish, institutional "
                             "population included" + (" (the City and the rest of the parish "
                                                      "together)" if len(book_names) > 1
                                                      else "") + "."),
            sex_ratio=measure(round(1000 * men / women), unit="males_per_1000_females",
                              year=YEAR, source=SOURCE_BOOK),
            sex_ratio_note="Men per thousand women, Table 5.1.",
            median_age=measure(median_age(years), unit="years", year=YEAR, source=SOURCE_BASE),
            median_age_note=("Interpolated within the single year holding the middle person of "
                             "the weighted 2011 household population"
                             + (f"; {round(unstated):,} of unstated age left out" if unstated
                                else "") + "."),
            ethnicity=present(dict(ethnic)), ethnicity_year=YEAR,
            ethnicity_note="Ethnic group (Q48) of the weighted 2011 household population.",
            religion=present(dict(religion)), religion_year=YEAR,
            religion_note=("Religion (Q49) of the weighted 2011 household population the "
                           "question was put to."),
            language=gap(NOT_AVAILABLE, LANGUAGE_GAP),
            sources=[{"field": "population/sex_ratio", "name": SOURCE_BOOK, "url": BOOK,
                      "year": YEAR},
                     {"field": "median_age/ethnicity/religion", "name": SOURCE_BASE,
                      "url": PORTAL, "year": YEAR}]))
    write_json(OUT, records)
    log(f"  wrote {OUT.name}: {len(records)} parishes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
