#!/usr/bin/env python3
"""Fiji: age and sex at the 2017 census, religion and ethnicity at the 2007 one.

Two tabulations of the Fiji Bureau of Statistics, one for each census that
answers a question at the level of the map's provinces:

* **2017 census, population by five-year age group and sex**, for the 15
  provinces and 4 divisions. The Bureau tabulated it in the Pacific
  Community's PopGIS and OCHA publishes it as the Common Operational Dataset
  for Fiji (``cod-ps-fji``), whose methodology line names its source: the
  Bureau's "2017 Population and Housing Census, Administrative Report". The
  map's provincial populations already come from it, so the median age and
  sex ratio here are of the same people. The Bureau publishes a median age
  only for the country (27.5 years in Release 1); the medians here are
  interpolated within the five-year group that holds the middle person.
* **2007 census, Table P01-3, "Relationship, Ethnicity, and Religion by
  Province of Enumeration, Fiji: 2007"**, from the Bureau's own document
  library (``doc_download/1256``), read from the Internet Archive's copy of
  March 2015 because the Bureau's current site no longer serves its old
  library. Its ethnicity block (eight groups) and religion block (18 Christian
  denominations, Hindu, Sikh, Moslem, other and none) are by province.

**Why 2007 for religion and ethnicity.** The 2017 census has published
neither: religion appears on none of the 484 pages of its Administrative
Report and General Tables (Release 3), Release 1 covers age, sex, geography
and economic activity, and the only two pages of Release 3 that say "ethnic"
quote the SDG disaggregation principle and the enumeration of Chinese
households. Language is published by neither census: the 2007 Analytical
Report (423 pages) names it once, as a question of the 1946 census, and the
2017 Release 3 on no page at all. So the 2007 table is
the latest one by province, and the records date it 2007 beside a 2017
population.

**What the map draws.** The provinces are drawn whole. The divisions are not:
the boundary file draws each one's main island and leaves the small ones out,
and for the Eastern Division -- Kadavu, Lau, Lomaiviti and Rotuma -- it draws
Kadavu alone: Lau, Lomaiviti and Rotuma have polygons only at the provincial
level. So the polygon labelled Eastern carries Kadavu's figures, and says so,
rather than putting four provinces' people on one island. Central, Northern
and Western carry their division's.

**Checks**, each refusing the run: the provinces of the age table add up to
Fiji's 884,887 and each division to its provinces; each province is within 1%
of the Bureau's own 2017 count (Release 1, Table 3) -- the PopGIS tabulation
places a few dozen people differently -- and Fiji's interpolated median is
within half a year of the published 27.5; every row's age groups and sexes
make its total. In Table P01-3 every column's relationship, ethnicity and
religion totals agree and equal the 2007 count Release 1 prints for the
province, the eight ethnic groups make the total exactly, the Christian row
is the sum of its denominations, and the religions printed leave at most 1%
of a province unaccounted for (895 people in all, whose religion the table
does not print).

Usage:
    python -m scripts.fetch_census.fiji_census
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, gap, http_get, log, measure, write_json
from .binding import fold
from .oceania_common import (
    bind_level, check, load_units, median_from_groups, population, sex_ratio, shares_of,
    summarise, unit_record,
)

OUT = "fiji_census.json"
OFFICE = "Fiji Bureau of Statistics"
YEAR = 2017
YEAR_2007 = 2007

COD_PACKAGE = "https://data.humdata.org/api/3/action/package_show?id=cod-ps-fji"
COD_PAGE = "https://data.humdata.org/dataset/cod-ps-fji"
COD_FILES = {"admin2": "fji_pplp_adm2_province_2017_v2.csv",
             "admin1": "fji_pplp_adm1_division_2017_v3.csv"}
AGES_SOURCE = (f"{OFFICE}, 2017 Population and Housing Census, population by five-year age "
               f"group and sex (PopGIS; OCHA COD-PS for Fiji)")

P013_ORIGINAL = ("http://www.statsfiji.gov.fj/index.php/document-library/doc_download/"
                 "1256-relationship-ethnicity-religion-by-province-of-enumeration-fiji-2007")
P013_URL = "http://web.archive.org/web/20150325124401id_/" + P013_ORIGINAL
P013_SOURCE = (f"{OFFICE}, 2007 Census of Population and Housing, Table P01-3: "
               f"Relationship, Ethnicity, and Religion by Province of Enumeration")
RELEASE_1_URL = ("https://www.statsfiji.gov.fj/download/121/phc-2017/727/"
                 "2017-population-and-housing-census-release-1.pdf")
RELEASE_3_URL = ("https://www.statsfiji.gov.fj/download/121/phc-2017/729/"
                 "2017-population-and-housing-census-release-3.pdf")
LICENCE = "None stated -- Fiji Bureau of Statistics publication, cited as such"

# The provinces in Table P01-3's column order, under the names the age table
# and the map use; and the count Release 1 (Table 3) prints for each, in 2007
# and in 2017.
PROVINCES = ("Ba", "Bua", "Cakaudrove", "Kadavu", "Lau", "Lomaiviti", "Macuata",
             "Nadroga/Navosa", "Naitasiri", "Namosi", "Ra", "Rewa", "Serua", "Tailevu",
             "Rotuma")
COUNT_2007 = dict(zip(PROVINCES, (231_760, 14_176, 49_344, 10_167, 10_683, 16_253, 72_441,
                                  58_387, 160_760, 6_898, 29_464, 100_995, 18_249, 55_692,
                                  2_002)))
COUNT_2017 = dict(zip(PROVINCES, (247_708, 15_466, 50_469, 10_897, 9_602, 15_657, 65_983,
                                  58_931, 177_678, 7_871, 30_432, 108_016, 20_031, 64_552,
                                  1_594)))
NATIONAL_2007 = 837_271
NATIONAL_2017 = 884_887
MEDIAN_2017 = 27.5          # Release 1: "The Median Age of the Population is 27.5 years"
# The header words Table P01-3 prints over its columns, hyphenated names split
# over two lines ("Cakau-/drove"); the second line's words, in order.
HEADER_WORDS = ("Total", "Ba", "Bua", "drove", "Kadavu", "Lau", "viti", "cuata", "Navosa",
                "tasiri", "osi", "Ra", "Rewa", "Serua", "levu", "uma")
DIVISIONS = {"Central": ("Naitasiri", "Namosi", "Rewa", "Serua", "Tailevu"),
             "Northern": ("Bua", "Cakaudrove", "Macuata"),
             "Western": ("Ba", "Nadroga/Navosa", "Ra"),
             "Eastern": ("Kadavu", "Lau", "Lomaiviti", "Rotuma")}
# The one province the boundary file draws of the Eastern Division.
EASTERN_DRAWN = "Kadavu"

# Table P01-3's row labels -- cut to fifteen characters by its layout -- and
# the names they are carried under.
ETHNIC_ROWS = {
    "Fijian": "Fijian (iTaukei)",
    "Indian": "Indo-Fijian",
    "Full/Part-Chines": "Chinese or part-Chinese",
    "European": "European",
    "Part-European": "Part-European",
    "Rotuman": "Rotuman",
    "Other Pacific Is": "Other Pacific Islanders",
    "Others": "Others",
}
DENOMINATIONS = {
    "Anglican": "Anglican",
    "Apostolic": "Apostolic Church",
    "Assembly of Go": "Assemblies of God",
    "All Nation Chr": "All Nations Christian Fellowship",
    "Baptist": "Baptist",
    "Catholic": "Roman Catholic",
    "Christ Mis Flw": "Christian Mission Fellowship",
    "Church of Chri": "Church of Christ",
    "Gospel": "Gospel",
    "Jehovah's Witn": "Jehovah's Witnesses",
    "Latter Day Sai": "Church of Jesus Christ of Latter-day Saints",
    "Methodist": "Methodist",
    "Penticostal": "Pentecostal",
    "Presbyterian": "Presbyterian",
    "Salvation Army": "Salvation Army",
    "Seventh Day Ad": "Seventh-day Adventist",
    "United Penteco": "United Pentecostal Church",
    "Other Christia": "Other Christian",
}
OTHER_FAITHS = {
    "Hindu": "Hinduism",
    "Sikh": "Sikhism",
    "Moslem": "Islam",
    "Other religion": "Other religion",
    "No religion": "No religion",
}
NUMBER = r"(?:\d{1,3}(?:,\d{3})+|\d{1,3}|-)"
ROW = re.compile(rf"^\s*(?P<label>[A-Za-z][A-Za-z'/ .-]*?)[\s.]*(?P<figures>{NUMBER}"
                 rf"(?:\s+{NUMBER})*)\s*$")


def figures_of(text: str) -> list[int]:
    return [0 if f == "-" else int(f.replace(",", "")) for f in text.split()]


# ---------------------------------------------------------------------------
# The 2017 age table
# ---------------------------------------------------------------------------

AGE = re.compile(r"^([MFT])_(\d{2})_(\d{2})$")
OPEN = re.compile(r"^([MFT])_(\d{2})plus$", re.I)


def age_rows(text: str, name_col: str, parent_col: str | None) -> dict[str, dict[str, Any]]:
    """{unit: {parent, total, male, female, groups}} from one COD-PS age table."""
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    columns = [c.strip() for c in reader.fieldnames or []]
    closed = sorted({(int(m.group(2)), int(m.group(3))) for c in columns
                     if (m := AGE.match(c))})
    opens = sorted({int(m.group(2)) for c in columns if (m := OPEN.match(c))})
    check(len(opens) == 1, f"fiji_census: {opens} open-ended age groups, expected one")
    check(closed and closed[0][0] == 0
          and all(b[0] == a[1] + 1 for a, b in zip(closed, closed[1:]))
          and closed[-1][1] + 1 == opens[0],
          f"fiji_census: age groups {closed} + {opens} do not run from 0 without a gap")
    top = next(c for c in columns if OPEN.match(c) and c.startswith("T"))
    # The table ends with its own totals by sex, which the groups must make.
    extra = [c for c in columns if re.match(r"^[MFT]_", c) and not AGE.match(c)
             and not OPEN.match(c)]
    totals = {c[0]: c for c in extra}
    check(len(extra) in (0, 3) and len(totals) == len(extra),
          f"fiji_census: columns {extra} are neither age groups nor one total per sex")
    out: dict[str, dict[str, Any]] = {}
    for raw in reader:
        row = {(k or "").strip(): (v or "").strip() for k, v in raw.items()}
        name = row[name_col]
        groups, males, females = [], 0, 0
        for low, high in closed:
            m, f, t = (int(row[f"{s}_{low:02d}_{high:02d}"]) for s in "MFT")
            check(m + f == t, f"fiji_census: {name} {low}-{high}: {m} + {f} != {t}")
            groups.append((low, high, t))
            males, females = males + m, females + f
        m, f = (int(row[top.replace("T", s, 1)]) for s in "MF")
        t = int(row[top])
        check(m + f == t, f"fiji_census: {name} {opens[0]}+: {m} + {f} != {t}")
        groups.append((opens[0], None, t))
        males, females = males + m, females + f
        if totals:
            printed = {k: int(row[c]) for k, c in totals.items()}
            check(printed == {"M": males, "F": females, "T": males + females},
                  f"fiji_census: {name}'s groups make {males:,} males and {females:,} "
                  f"females; its totals say {printed}")
        out[name] = {"parent": row.get(parent_col, "") if parent_col else "",
                     "total": males + females, "male": males, "female": females,
                     "groups": groups}
    return out


def check_ages(provinces: dict[str, dict[str, Any]],
               divisions: dict[str, dict[str, Any]]) -> None:
    """The age tables against each other and against the Bureau's own count."""
    check(set(provinces) == set(PROVINCES),
          f"fiji_census: the age table's provinces are {sorted(provinces)}")
    check(set(divisions) == set(DIVISIONS),
          f"fiji_census: the age table's divisions are {sorted(divisions)}")
    total = sum(p["total"] for p in provinces.values())
    check(total == NATIONAL_2017,
          f"fiji_census: the provinces add up to {total:,}, not Fiji's {NATIONAL_2017:,}")
    for division, members in DIVISIONS.items():
        summed = sum(provinces[p]["total"] for p in members)
        check(summed == divisions[division]["total"],
              f"fiji_census: {division}'s provinces add up to {summed:,}, not "
              f"{divisions[division]['total']:,}")
        for p in members:
            check(provinces[p]["parent"] == division,
                  f"fiji_census: {p} is in {provinces[p]['parent']!r}, not {division}")
    for name, unit in provinces.items():
        printed = COUNT_2017[name]
        check(abs(unit["total"] - printed) <= 0.01 * printed,
              f"fiji_census: {name} has {unit['total']:,} in the age table and "
              f"{printed:,} in Release 1")
    groups: dict[tuple[int, int | None], float] = {}
    for unit in provinces.values():
        for low, high, n in unit["groups"]:
            groups[(low, high)] = groups.get((low, high), 0) + n
    median = median_from_groups([(lo, hi, n) for (lo, hi), n in groups.items()])
    check(median is not None and abs(median - MEDIAN_2017) <= 0.5,
          f"fiji_census: Fiji's interpolated median is {median}, the Bureau's {MEDIAN_2017}")
    log(f"  2017 ages: 15 provinces adding to {total:,} and to their divisions; Fiji's "
        f"interpolated median {median} against the published {MEDIAN_2017}")


# ---------------------------------------------------------------------------
# Table P01-3 (2007)
# ---------------------------------------------------------------------------

def read_p013(pages: list[str]) -> dict[str, dict[str, Any]]:
    """{province: {total, ethnicity {label: n}, religion {label: n}}} from page one."""
    page = next((p for p in pages if "Table P01-3." in p and "***" not in p.split("\n")[0]),
                None)
    check(page is not None, "fiji_census: no page carries Table P01-3 for all of Fiji")
    lines = page.splitlines()
    header = next((ln for ln in lines if "Kadavu" in ln and "Rewa" in ln and "Total" in ln),
                  "")
    words = tuple(re.findall(r"[A-Za-z]+", header))
    check(words[-len(HEADER_WORDS):] == HEADER_WORDS,
          f"fiji_census: Table P01-3's columns read {words}, not {HEADER_WORDS}")
    section, blocks = None, {"RELATIONSHIP": [], "ETHNICITY": [], "RELIGION": []}
    for line in lines:
        head = line.strip()
        if head in blocks:
            section = head
            continue
        match = ROW.match(line)
        if section is None or not match:
            continue
        figures = figures_of(match.group("figures"))
        if len(figures) != 1 + len(PROVINCES):
            continue
        label = re.sub(r"[\s.]+$", "", match.group("label")).strip()
        check(sum(figures[1:]) == figures[0],
              f"fiji_census: P01-3 row {label!r} has provinces adding to "
              f"{sum(figures[1:]):,}, not its total {figures[0]:,}")
        blocks[section].append((label, figures))
    totals = {name: [f for label, f in rows if label == "Total"]
              for name, rows in blocks.items()}
    for name, found in totals.items():
        check(len(found) == 1, f"fiji_census: P01-3's {name} block has {len(found)} totals")
    total = totals["RELATIONSHIP"][0]
    check(totals["ETHNICITY"][0] == total and totals["RELIGION"][0] == total,
          "fiji_census: P01-3's three blocks have different totals")
    check(total[0] == NATIONAL_2007, f"fiji_census: P01-3 counts {total[0]:,}, not "
                                     f"{NATIONAL_2007:,}")
    for name, count in zip(PROVINCES, total[1:]):
        check(count == COUNT_2007[name], f"fiji_census: P01-3 has {name} at {count:,}, "
                                         f"Release 1 at {COUNT_2007[name]:,}")

    ethnic = {label: f for label, f in blocks["ETHNICITY"] if label != "Total"}
    check(set(ethnic) == set(ETHNIC_ROWS),
          f"fiji_census: P01-3's ethnic rows are {sorted(ethnic)}")
    faiths = {label: f for label, f in blocks["RELIGION"] if label not in ("Total",)}
    known = set(DENOMINATIONS) | set(OTHER_FAITHS) | {"Christian"}
    check(set(faiths) == known, f"fiji_census: P01-3's religion rows are {sorted(faiths)}; "
                                f"unread {sorted(known - set(faiths))}, unknown "
                                f"{sorted(set(faiths) - known)}")
    out: dict[str, dict[str, Any]] = {}
    for i, name in enumerate(PROVINCES, start=1):
        people = total[i]
        eth = {ETHNIC_ROWS[k]: v[i] for k, v in ethnic.items()}
        check(sum(eth.values()) == people,
              f"fiji_census: {name}'s ethnic groups add up to {sum(eth.values()):,}, "
              f"not {people:,}")
        denominations = {DENOMINATIONS[k]: faiths[k][i] for k in DENOMINATIONS}
        check(sum(denominations.values()) == faiths["Christian"][i],
              f"fiji_census: {name}'s denominations do not add up to its Christians")
        rel = denominations | {OTHER_FAITHS[k]: faiths[k][i] for k in OTHER_FAITHS}
        unprinted = people - sum(rel.values())
        check(0 <= unprinted <= 0.01 * people,
              f"fiji_census: {name}'s religions leave {unprinted:,} of {people:,} unprinted")
        out[name] = {"total": people, "ethnicity": eth, "religion": rel,
                     "unprinted": unprinted}
    log(f"  2007 Table P01-3: 15 provinces adding to {total[0]:,}; religion unprinted for "
        f"{sum(p['unprinted'] for p in out.values()):,} people")
    return out


def summed(units: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {"total": 0, "ethnicity": {}, "religion": {}, "unprinted": 0}
    for unit in units:
        out["total"] += unit["total"]
        out["unprinted"] += unit["unprinted"]
        for field in ("ethnicity", "religion"):
            for label, n in unit[field].items():
                out[field][label] = out[field].get(label, 0) + n
    return out


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------

LANGUAGE_GAP = (
    "Neither of Fiji's last two censuses publishes language. The 2007 census's 423-page "
    "Analytical Report mentions language once, to say that the 1946 census asked it, and its "
    "tables by province carry relationship, ethnicity and religion; the word appears on none "
    "of the 484 pages of the 2017 census's Administrative Report and General Tables, and "
    "its Release 1 covers age, sex, geography and economic activity.")
COMPOSITION_NOTE = (
    "{what} at the 2007 census, the latest by province: Table P01-3 of the Fiji Bureau of "
    "Statistics (by province of enumeration). The 2017 census has published no {what_l} "
    "table: {why}{extra}")
WHY_RELIGION = ("the word appears on none of the 484 pages of its Administrative Report and "
                "General Tables, and its Release 1 covers age, sex, geography and economic "
                "activity.")
WHY_ETHNICITY = ("its Administrative Report and General Tables (484 pages) tabulate no "
                 "ethnic group, and its Release 1 covers age, sex, geography and economic "
                 "activity.")
ETHNIC_TERMS = (" The census's \"Fijian\" is the indigenous iTaukei people and its \"Indian\" "
                "the Indo-Fijian community, named here as they are today.")
MEDIAN_NOTE = (
    "Interpolated within the five-year age group that holds the middle person, from the "
    "2017 census's population by age and sex (the Fiji Bureau of Statistics' tabulation "
    "in PopGIS, published by OCHA as COD-PS). The Bureau publishes a median only for Fiji "
    "as a whole, 27.5 years.")
SEX_NOTE = "Males per 100 females, 2017 census, from the same table."


def fields_for(ages: dict[str, Any], composition: dict[str, Any]) -> dict[str, Any]:
    median = median_from_groups(ages["groups"])
    unprinted = composition["unprinted"]
    religion_extra = (f" The table prints no religion for {unprinted:,} of the "
                      f"{composition['total']:,} people here, and they are in no share."
                      if unprinted else "")
    return {
        "median_age": measure(median, unit="years", year=YEAR, source=AGES_SOURCE),
        "median_age_note": MEDIAN_NOTE,
        "sex_ratio": measure(sex_ratio(ages["male"], ages["female"]),
                             unit="males_per_100_females", year=YEAR, source=AGES_SOURCE),
        "sex_ratio_note": SEX_NOTE,
        "religion": shares_of(composition["religion"], composition["total"]),
        "religion_year": YEAR_2007,
        "religion_note": COMPOSITION_NOTE.format(what="Religion", what_l="religion",
                                                 why=WHY_RELIGION, extra=religion_extra),
        "ethnicity": shares_of(composition["ethnicity"], composition["total"]),
        "ethnicity_year": YEAR_2007,
        "ethnicity_note": COMPOSITION_NOTE.format(what="Ethnicity", what_l="ethnicity",
                                                  why=WHY_ETHNICITY, extra=ETHNIC_TERMS),
        "language": gap(NOT_AVAILABLE, LANGUAGE_GAP),
    }


SOURCES = [
    {"field": "median_age/sex_ratio", "name": AGES_SOURCE, "url": COD_PAGE, "year": YEAR,
     "license": "Creative Commons Attribution for Intergovernmental Organisations"},
    {"field": "religion/ethnicity", "name": P013_SOURCE, "url": P013_ORIGINAL,
     "archived": P013_URL, "year": YEAR_2007, "license": LICENCE},
    {"field": "controls", "name": f"{OFFICE}, 2017 Population and Housing Census, Release 1",
     "url": RELEASE_1_URL, "year": YEAR, "license": LICENCE},
]


def build(provinces: dict[str, dict[str, Any]], divisions: dict[str, dict[str, Any]],
          p013: dict[str, dict[str, Any]], admin1: list[dict[str, Any]],
          admin2: list[dict[str, Any]]) -> list[dict[str, Any]]:
    check_ages(provinces, divisions)
    parents = {u["id"]: u["name"] for u in admin1}
    division_of = {p: d for d, members in DIVISIONS.items() for p in members}
    province_units = bind_level({p: (p, division_of[p]) for p in PROVINCES}, admin2, parents)
    division_units = bind_level({d: (d, "") for d in DIVISIONS}, admin1, {})
    records = []
    for division, unit in division_units.items():
        if division == "Eastern":
            own = EASTERN_DRAWN
            fields = fields_for(provinces[own], p013[own])
            whole = sum(provinces[p]["total"] for p in DIVISIONS["Eastern"])
            fields["population"] = population(provinces[own]["total"], YEAR, AGES_SOURCE)
            fields["population_note"] = (
                f"Kadavu's own count. The boundary file draws the Eastern Division as Kadavu "
                f"alone -- Lau, Lomaiviti and Rotuma have polygons only at the provincial "
                f"level -- so this polygon carries Kadavu's figures throughout. The Eastern "
                f"Division as a whole had {whole:,} people at the 2017 census.")
        else:
            members = DIVISIONS[division]
            fields = fields_for(divisions[division], summed([p013[p] for p in members]))
            fields["religion_note"] += (" The division's provinces added up: "
                                        + ", ".join(members) + ".")
            fields["ethnicity_note"] += (" The division's provinces added up: "
                                         + ", ".join(members) + ".")
        records.append(unit_record("FJI", division, unit["name"], unit, "admin1", None,
                                   SOURCES, **fields))
    for province, unit in province_units.items():
        fields = fields_for(provinces[province], p013[province])
        parent = parents.get(unit.get("parent"))
        records.append(unit_record("FJI", province, unit["name"], unit, "admin2", parent,
                                   SOURCES, aliases=[province], **fields))
    return records


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------

def cod_tables() -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    package = json.loads(http_get(COD_PACKAGE, cache=False))["result"]
    urls = {str(r.get("name", "")).lower(): r["url"] for r in package.get("resources", [])}
    texts = {}
    for level, name in COD_FILES.items():
        check(name in urls, f"fiji_census: {COD_PACKAGE} lists no {name}")
        text = http_get(urls[name], cache=False)
        check(isinstance(text, str), f"fiji_census: {name} is not text")
        texts[level] = text
    provinces = age_rows(texts["admin2"], "ADM2_EN", "ADM1_EN")
    divisions = age_rows(texts["admin1"], "ADM1_EN", None)
    return provinces, divisions


def p013_pages() -> list[str]:
    from pypdf import PdfReader  # noqa: PLC0415
    blob = http_get(P013_URL, binary=True, timeout=300)
    check(isinstance(blob, bytes) and blob[:5] == b"%PDF-",
          f"fiji_census: {P013_URL} is not a PDF")
    reader = PdfReader(io.BytesIO(blob))
    return [(page.extract_text() or "") for page in reader.pages]


def main() -> int:
    argparse.ArgumentParser(description=__doc__,
                            formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    log("fiji_census: 2017 ages by province and division; 2007 religion and ethnicity")
    provinces, divisions = cod_tables()
    p013 = read_p013(p013_pages())
    records = build(provinces, divisions, p013, load_units("FJI", "admin1"),
                    load_units("FJI", "admin2"))
    log("  " + summarise(records))
    write_json(PROCESSED / OUT, records)
    log(f"  wrote {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
