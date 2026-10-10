#!/usr/bin/env python3
"""Solomon Islands, 2019 Census: population, age, sex, religion and ethnic group.

The Solomon Islands National Statistics Office's **2019 Population and
Housing Census, Report Volume 2: Basic Tables and Census Description** (318
pages) prints its tables by province and by ward, the 183 wards of the
provincial assemblies:

* **P2.2**: population by sex, by ward;
* **P3.1**: population by five-year age group to an open 85+, by province and
  ward, for the median age;
* **P8.3**: population by religious denomination, by province and ward;
* **P8.4**: population by ethnic group and province.

**Constituencies are wards added up.** The map's second level is the 50
national constituencies, which the census does not tabulate; each is a set
of whole wards. Which wards make which constituency is read from OCHA's
Common Operational Dataset for the Solomon Islands (``cod-ps-slb``, from the
Government of Solomon Islands): its ward table carries every ward's
constituency, and its ward code ends in the census's own ward number within
the province ("SB0404300403" is Central's ward 03, East Gela, in Nggela).
The ward's name in the census and in that table must agree, or the run stops.
Temotu Pele, the Reef Islands constituency, has no polygon on the map.

**What is not tabulated below the province**: ethnic group (P8.4 is by
province only). The census asked the first language learnt as a child of
everyone aged five and over, but the National Report (Volume 1, Table 9.6.1)
counts each language's speakers for the country, listed under the province
the language belongs to, and the Basic Tables publish only literacy by
language (P9.7, P9.8); so language is left with that reason at both levels.

**Checks**, each refusing the run: the country is 720,956 people; every row's
males and females make its total; a province's wards make the province;
every row's age groups and denominations make its total and that total is
P2.2's; the medians P3.1 gives the country and each province are within 0.3
years of the ones the volume's "Summary of main indicators" prints (they
agree to the tenth); every ward is read from all three tables and found in
the ward table once; every drawn constituency and province is bound once.

Usage:
    python -m scripts.fetch_census.solomon_census
"""

from __future__ import annotations

import argparse
import csv
import difflib
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

YEAR = 2019
OUT = "solomon_census.json"
OFFICE = "Solomon Islands National Statistics Office"
SOURCE = (f"{OFFICE}, 2019 Population and Housing Census, Report Volume 2: Basic Tables "
          "and Census Description")
URL = ("https://statistics.gov.sb/download/60/solomon-islands-2019-population-and-housing-"
       "census-national-report_volume-1-and-2/1207/solomon-islands-2019-census-report-vol-2_"
       "basic-tables_operations.pdf")
WARDS_PACKAGE = "https://data.humdata.org/api/3/action/package_show?id=cod-ps-slb"
WARDS_PAGE = "https://data.humdata.org/dataset/cod-ps-slb"
WARDS_FILE = "slb_admpop_adm3_2023.csv"
NATIONAL = 720_956
WARD_COUNT = 183

# Each table's figures to a row.
WIDTHS = {"P2.2": 5, "P3.1": 19, "P8.3": 18, "P8.4": 13}
PROVINCES = {"01": "Choiseul", "02": "Western", "03": "Isabel", "04": "Central",
             "05": "Rennell-Bellona", "06": "Guadalcanal", "07": "Malaita",
             "08": "Makira-Ulawa", "09": "Temotu", "10": "Honiara"}
PROVINCE_NAMES = {fold(n): c for c, n in PROVINCES.items()} | {
    fold("Honiara City Council"): "10", fold("Rennell Bellona"): "05",
    fold("Makira"): "08"}
# The census's province -> the boundary file's first-level label.
PROVINCE_ON_MAP = {"Choiseul": "Choiseul", "Western": "Western", "Isabel": "Isabel",
                   "Central": "Central", "Rennell-Bellona": "Rennell and Bellona",
                   "Guadalcanal": "Guadalcanal", "Malaita": "Malaita",
                   "Makira-Ulawa": "Makira", "Temotu": "Temotu",
                   "Honiara": "Capital Territory (Honiara)"}
UNDRAWN = {"Temotu Pele"}

AGE_GROUPS = [(0, 4), (5, 9), (10, 14), (15, 19), (20, 24), (25, 29), (30, 34), (35, 39),
              (40, 44), (45, 49), (50, 54), (55, 59), (60, 64), (65, 69), (70, 74), (75, 79),
              (80, 84), (85, None)]
# P8.3's denominations in column order, in the census's own names (the
# Muslim column is Islam's; "No Religion or Faith/Atheism" is no religion).
RELIGIONS = ("Church of Melanesia", "Roman Catholic", "South Sea Evangelical Church",
             "Seventh-day Adventist", "United Church", "Christian Fellowship Church",
             "Christian Outreach Church", "Pentecostal", "Jehovah's Witnesses", "Baha'i",
             "Assemblies of God", "Islam", "Baptist", "Other religions",
             "Custom beliefs or animism", "No religion", "Refused to answer")
# P8.4's ethnic groups in column order.
ETHNIC = ("Melanesian", "Polynesian", "Micronesian", "Chinese", "European",
          "Micronesian-Melanesian", "Micronesian-Polynesian", "Australian",
          "New Zealander/Maori", "Malaysian", "Indonesian", "Others")

NUMBER = re.compile(r"^(?:\d{1,3}(?:,\d{3})+|\d+|-)$")
TITLE = re.compile(r"\b(P\d+\.\d+)\s*:")
CODE = re.compile(r"^\d{2}$")


def figures(tokens: list[str]) -> list[float]:
    return [0.0 if t == "-" else float(t.replace(",", "")) for t in tokens]


# ---------------------------------------------------------------------------
# Reading the PDF's text
# ---------------------------------------------------------------------------

# Tables printed again for males and females under the same title: the first
# panel, all persons, is the one read, and its totals are checked against P2.2.
PANELLED = {"P8.4"}


def read_table(pages: list[str], table: str) -> dict[str, Any]:
    """{"national": figures, "provinces": {code: figures}, "wards": {(code, nn): (name, figures)}}.

    A row is a ward's two-digit number and name, or a province's name (with
    its code or without), then the table's figures. Rows are filed under the
    province row that last preceded them -- on an earlier page if the table
    runs on -- and under the table title that last preceded them, so a page's
    leftover text from a neighbouring table is not read as this one's.
    """
    width = WIDTHS[table]
    out: dict[str, Any] = {"national": None, "provinces": {}, "wards": {}}

    def put(bucket: dict, key: Any, value: Any, what: str) -> None:
        if key in bucket and table in PANELLED:
            return
        if key in bucket:
            check(bucket[key] == value,
                  f"solomon_census: {table} prints {what} twice with different figures")
        else:
            bucket[key] = value

    current = province = None
    wrapped: list[str] = []
    for page in pages:
        for raw in page.splitlines():
            line = " ".join(raw.split())
            titles = TITLE.findall(line)
            if titles:
                # A table's pages each repeat its title, and its wards run on
                # from the last page's province; a new table starts afresh.
                if titles[-1] != current:
                    province = None
                current = titles[-1]
                continue
            if current != table:
                continue
            tokens = line.split()
            if len(tokens) <= width or not all(NUMBER.match(t) for t in tokens[-width:]):
                # A province's name too long for its cell is printed over two
                # lines, "10 Honiara City" above "Council 129,569 ...".
                wrapped = tokens
                continue
            head, values = tokens[:-width], figures(tokens[-width:])
            joined = wrapped + head
            if (not CODE.match(head[0]) and wrapped
                    and fold(" ".join(joined[1:] if CODE.match(joined[0]) else joined))
                    in PROVINCE_NAMES):
                head = joined
            wrapped = []
            code = head[0] if CODE.match(head[0]) else None
            name = " ".join(head[1:] if code else head)
            if not name:
                continue
            if fold(name) in PROVINCE_NAMES:
                province = PROVINCE_NAMES[fold(name)]
                put(out["provinces"], province, values, PROVINCES[province])
            elif fold(name) in (fold("Solomon Islands"), fold("Total")):
                if out["national"] is None:
                    out["national"] = values
            elif code and province:
                key = (province, code)
                if key in out["wards"]:
                    check(fold(out["wards"][key][0]) == fold(name),
                          f"solomon_census: {table} files {name} as {PROVINCES[province]}'s "
                          f"ward {code}, which is {out['wards'][key][0]}: a province row was "
                          "not read")
                put(out["wards"], key, (name, values), f"ward {name}")
    return out


def read_population(pages: list[str]) -> dict[str, Any]:
    table = read_table(pages, "P2.2")
    check(table["national"] is not None and table["national"][0] == NATIONAL,
          f"solomon_census: P2.2 reads the country as {table['national']}")
    check(sorted(table["provinces"]) == sorted(PROVINCES),
          f"solomon_census: P2.2 has provinces {sorted(table['provinces'])}")
    counts = {PROVINCES[c]: sum(1 for p, _ in table["wards"] if p == c) for c in PROVINCES}
    check(len(table["wards"]) == WARD_COUNT,
          f"solomon_census: P2.2 has {len(table['wards'])} wards, not {WARD_COUNT}: {counts}")
    for rows in (table["provinces"].values(),
                 (v for _, v in table["wards"].values())):
        for values in rows:
            check(values[1] + values[2] == values[0],
                  f"solomon_census: P2.2 males and females do not make {values[0]:,.0f}")
    for code, values in table["provinces"].items():
        made = sum(v[0] for (p, _), (_, v) in table["wards"].items() if p == code)
        check(made == values[0],
              f"solomon_census: {PROVINCES[code]}'s wards make {made:,.0f}, not {values[0]:,.0f}")
    check(sum(v[0] for v in table["provinces"].values()) == NATIONAL,
          "solomon_census: the provinces do not make the country")
    return table


def read_breakdown(pages: list[str], table: str, people: dict[str, Any]) -> dict[str, Any]:
    """P3.1 or P8.3: every province and ward's breakdown, checked against P2.2."""
    rows = read_table(pages, table)
    check(sorted(rows["provinces"]) == sorted(PROVINCES),
          f"solomon_census: {table} has provinces {sorted(rows['provinces'])}")
    missing = sorted(set(people["wards"]) - set(rows["wards"]))
    check(not missing, f"solomon_census: {table} has no row for wards {missing}")

    def checked(values: list[float], total: float, what: str) -> list[float]:
        check(sum(values[1:]) == values[0] and values[0] == total,
              f"solomon_census: {table} {what}: cells make {sum(values[1:]):,.0f}, total "
              f"{values[0]:,.0f}, P2.2 {total:,.0f}")
        return values[1:]

    out = {"provinces": {}, "wards": {}}
    for code, values in rows["provinces"].items():
        out["provinces"][code] = checked(values, people["provinces"][code][0], PROVINCES[code])
    for key, (name, values) in rows["wards"].items():
        if key in people["wards"]:
            out["wards"][key] = checked(values, people["wards"][key][1][0], name)
    return out


def read_ethnicity(pages: list[str], people: dict[str, Any]) -> dict[str, list[float]]:
    rows = read_table(pages, "P8.4")
    check(sorted(rows["provinces"]) == sorted(PROVINCES),
          f"solomon_census: P8.4 has provinces {sorted(rows['provinces'])}")
    out = {}
    for code, values in rows["provinces"].items():
        total = people["provinces"][code][0]
        check(sum(values[1:]) == values[0] == total,
              f"solomon_census: P8.4 {PROVINCES[code]}: groups make {sum(values[1:]):,.0f}, "
              f"total {values[0]:,.0f}, P2.2 {total:,.0f}")
        out[code] = values[1:]
    return out


# ---------------------------------------------------------------------------
# Wards -> constituencies
# ---------------------------------------------------------------------------

def ward_table(text: str) -> dict[tuple[str, str], dict[str, str]]:
    """{(province code, ward number): {names, constituency, constituency code, province}}."""
    out: dict[tuple[str, str], dict[str, str]] = {}
    for row in csv.DictReader(io.StringIO(text)):
        pcode = (row.get("ADM3_PCODE") or "").strip()
        check(re.fullmatch(r"SB\d{10}", pcode) is not None,
              f"solomon_census: ward code {pcode!r} is not SB and ten digits")
        key = (pcode[2:4], pcode[-2:])
        check(key not in out, f"solomon_census: two wards carry {key}")
        out[key] = {"names": {(row.get("ADM3_NAME") or "").strip(),
                              (row.get("ADM3_NAME_ALT") or "").strip()} - {""},
                    "constituency": (row.get("ADM2_NAME") or "").strip(),
                    "code": (row.get("ADM2_PCODE") or "").strip(),
                    "province": (row.get("ADM1_NAME") or "").strip()}
    return out


def assign_wards(people: dict[str, Any], wards: dict[tuple[str, str], dict[str, str]]
                 ) -> dict[tuple[str, str], str]:
    """{census ward: constituency code}, refusing a ward whose names disagree."""
    check(set(wards) == set(people["wards"]),
          f"solomon_census: the ward table has {sorted(set(wards) ^ set(people['wards']))} "
          "where the census has not, or the other way round")
    out = {}
    for key, (name, _) in people["wards"].items():
        known = wards[key]["names"]
        if fold(name) not in {fold(n) for n in known}:
            best = max(difflib.SequenceMatcher(None, fold(name), fold(n)).ratio()
                       for n in known)
            check(best >= 0.6, f"solomon_census: census ward {key} {name!r} is "
                               f"{sorted(known)} in the ward table")
            log(f"  ward {PROVINCES[key[0]]} {key[1]}: census {name!r}, ward table "
                f"{sorted(known)}")
        out[key] = wards[key]["code"]
    return out


def add_up(keys: list[tuple[str, str]], table: dict[tuple[str, str], list[float]]
           ) -> list[float]:
    return [sum(table[k][i] for k in keys) for i in range(len(table[keys[0]]))]


# The Basic Tables' "Summary of main indicators" (p. vii) prints, for the
# country, its urban and rural sectors and the ten provinces in code order,
# each column's population and median age. The medians computed here from
# P3.1 must be the office's own to within MEDIAN_SLACK years, the country's
# included; the population row places the columns, each province's being its
# P2.2 total.
SUMMARY = "SUMMARY OF MAIN INDICATORS"
SUMMARY_ROWS = ("Total Population", "Median age")
SUMMARY_COLUMNS = 3 + len(PROVINCES)
MEDIAN_SLACK = 0.3
SUMMARY_CELL = re.compile(r"\d{1,3}(?:,\d{3})*(?:\.\d)?")


def summary_rows(pages: list[str]) -> dict[str, list[float]]:
    """The summary page's population and median-age rows, a figure a column."""
    for page in pages:
        if SUMMARY not in page:
            continue
        rows: dict[str, list[float]] = {}
        for line in page.splitlines():
            line = " ".join(line.split())
            for label in SUMMARY_ROWS:
                if line.startswith(label + " ") and label not in rows:
                    cells = line[len(label):].split()
                    if (len(cells) == SUMMARY_COLUMNS
                            and all(SUMMARY_CELL.fullmatch(c) for c in cells)):
                        rows[label] = [float(c.replace(",", "")) for c in cells]
        if set(rows) == set(SUMMARY_ROWS):
            return rows
    raise SystemExit("solomon_census: no summary of main indicators with a population and a "
                     f"median-age row of {SUMMARY_COLUMNS} figures")


def grouped(counts: list[float]) -> float | None:
    return median_from_groups([(lo, hi, n) for (lo, hi), n in zip(AGE_GROUPS, counts)])


def check_medians(pages: list[str], people: dict[str, Any], ages: dict[str, Any]
                  ) -> dict[str, tuple[float | None, float]]:
    """{column: (computed, printed)} for the country and every province, all within slack."""
    rows = summary_rows(pages)
    population, printed = rows["Total Population"], rows["Median age"]
    check(population[0] == NATIONAL,
          f"solomon_census: the summary's first column counts {population[0]:,.0f}, not "
          f"{NATIONAL:,}")
    national = [sum(v[i] for v in ages["provinces"].values()) for i in range(len(AGE_GROUPS))]
    out = {"Solomon Islands": (grouped(national), printed[0])}
    for i, code in enumerate(sorted(PROVINCES)):
        column = 3 + i
        check(population[column] == people["provinces"][code][0],
              f"solomon_census: the summary's column {column + 1} counts "
              f"{population[column]:,.0f}, and P2.2 {PROVINCES[code]} "
              f"{people['provinces'][code][0]:,.0f}")
        out[PROVINCES[code]] = (grouped(ages["provinces"][code]), printed[column])
    for name, (computed, published) in out.items():
        check(computed is not None and abs(computed - published) <= MEDIAN_SLACK,
              f"solomon_census: {name}'s median age is {computed} from P3.1, and the summary "
              f"of main indicators prints {published}")
    log("  median ages from P3.1 against the summary of main indicators: "
        + ", ".join(f"{n} {c} ({p})" for n, (c, p) in out.items()))
    return out


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------

NOTES = {
    "population_note": "Total population, 2019 Census (Basic Tables, P2.2).",
    "sex_ratio_note": "Males per 100 females, 2019 Census (P2.2).",
    "median_age_note": (
        "Interpolated within the five-year age group that holds the middle person, from the "
        "2019 Census's population by five-year age group to an open 85 and over (P3.1)."),
    "religion_note": (
        "Religious denomination, 2019 Census (P8.3), in the census's own denominations; "
        "'Islam' is its 'Muslim' and 'No religion' its 'No Religion or Faith/Atheism'."),
}
LANGUAGE = gap(NOT_AVAILABLE, (
    "The 2019 Census asked the first language learnt as a child of everyone aged five and "
    "over, and publishes it for the country only: the National Report's Table 9.6.1 counts "
    "the speakers of Pidgin and of the larger local languages nationally, listing each "
    "language under the province it belongs to rather than where its speakers live, and "
    "the Basic Tables give literacy by language (P9.7, P9.8). No table gives first language "
    "for a province, a ward or a constituency."))
WARD_ETHNICITY = gap(NOT_AVAILABLE, (
    "The 2019 Census tabulates ethnic group by province only (Basic Tables, P8.4); no "
    "table gives it for a ward or a constituency."))
CONSTITUENCY_NOTE = (
    " A constituency's figures are its wards' added up: the census tabulates wards, and "
    "which wards make the constituency is taken from OCHA's Common Operational Dataset "
    "(cod-ps-slb).")


def fields_for(people: list[float], ages: list[float], religion: list[float],
               ethnicity: list[float] | None, constituency: bool) -> dict[str, Any]:
    median = median_from_groups([(lo, hi, n) for (lo, hi), n in zip(AGE_GROUPS, ages)])
    fields: dict[str, Any] = {
        "population": population(people[0], YEAR, f"{SOURCE} (P2.2)"),
        "sex_ratio": measure(sex_ratio(people[1], people[2]), unit="males_per_100_females",
                             year=YEAR, source=SOURCE),
        "median_age": (measure(median, unit="years", year=YEAR, source=SOURCE)
                       if median is not None else None),
        "religion": shares_of(dict(zip(RELIGIONS, religion)), people[0]),
        "religion_year": YEAR,
        "language": LANGUAGE,
        **NOTES,
    }
    if ethnicity is not None:
        fields.update({
            "ethnicity": shares_of(dict(zip(ETHNIC, ethnicity)), people[0]),
            "ethnicity_year": YEAR,
            "ethnicity_note": "Ethnic group, 2019 Census (P8.4).",
        })
    else:
        fields["ethnicity"] = WARD_ETHNICITY
    if constituency:
        for key in ("population_note", "sex_ratio_note", "median_age_note", "religion_note"):
            fields[key] += CONSTITUENCY_NOTE
    return fields


SOURCES = [
    {"field": "population/median_age/sex_ratio/religion/ethnicity", "name": SOURCE,
     "url": URL, "year": YEAR,
     "license": "None stated -- Solomon Islands National Statistics Office publication, "
                "cited as such"},
    {"field": "wards making each constituency",
     "name": "OCHA, Common Operational Dataset -- population statistics (cod-ps-slb), ward table",
     "url": WARDS_PAGE, "year": 2023, "license": "CC BY-IGO"},
]


def build(pages: list[str], wards: dict[tuple[str, str], dict[str, str]],
          admin1: list[dict[str, Any]], admin2: list[dict[str, Any]]) -> list[dict[str, Any]]:
    people = read_population(pages)
    ages = read_breakdown(pages, "P3.1", people)
    religion = read_breakdown(pages, "P8.3", people)
    ethnicity = read_ethnicity(pages, people)
    constituency_of = assign_wards(people, wards)
    check_medians(pages, people, ages)

    members: dict[str, list[tuple[str, str]]] = {}
    for key, code in sorted(constituency_of.items()):
        members.setdefault(code, []).append(key)
    names = {code: wards[keys[0]]["constituency"] for code, keys in members.items()}
    provinces_of = {code: {k[0] for k in keys} for code, keys in members.items()}
    for code, found in provinces_of.items():
        check(len(found) == 1, f"solomon_census: constituency {names[code]} spans {found}")

    parents = {u["id"]: u["name"] for u in admin1}
    province_units = bind_level(
        {code: (PROVINCE_ON_MAP[name], "") for code, name in PROVINCES.items()}, admin1, {})
    drawn = {code: name for code, name in names.items() if name not in UNDRAWN}
    constituency_units = bind_level(
        {code: (name, PROVINCE_ON_MAP[PROVINCES[next(iter(provinces_of[code]))]])
         for code, name in drawn.items()}, admin2, parents)

    records = []
    for code, unit in province_units.items():
        fields = fields_for(people["provinces"][code], ages["provinces"][code],
                            religion["provinces"][code], ethnicity[code], constituency=False)
        records.append(unit_record("SLB", PROVINCES[code], unit["name"], unit, "admin1", None,
                                   SOURCES, **fields))
    for code, unit in constituency_units.items():
        keys = members[code]
        totals = [sum(people["wards"][k][1][i] for k in keys) for i in range(3)]
        fields = fields_for(totals, add_up(keys, ages["wards"]), add_up(keys, religion["wards"]),
                            None, constituency=True)
        fields["population_note"] += (
            f" Its {len(keys)} wards: " + ", ".join(people["wards"][k][0] for k in keys) + ".")
        province = PROVINCES[keys[0][0]]
        records.append(unit_record("SLB", code, names[code], unit, "admin2",
                                   PROVINCE_ON_MAP[province], SOURCES, **fields))
    for code, name in sorted(names.items()):
        if name in UNDRAWN:
            total = sum(people["wards"][k][1][0] for k in members[code])
            log(f"  no polygon: {name} ({total:,.0f} people in {len(members[code])} wards), "
                "counted in its province")
    return records


def page_texts(blob: bytes) -> list[str]:
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(blob))
    return [(page.extract_text() or "") for page in reader.pages]


def fetch_wards() -> dict[tuple[str, str], dict[str, str]]:
    package = json.loads(http_get(WARDS_PACKAGE, cache=False))["result"]
    url = next((r["url"] for r in package.get("resources", [])
                if str(r.get("name", "")).lower() == WARDS_FILE), None)
    check(url is not None, f"solomon_census: {WARDS_PACKAGE} lists no {WARDS_FILE}")
    text = http_get(url, cache=False)
    assert isinstance(text, str)
    return ward_table(text.lstrip("﻿"))


def main() -> int:
    argparse.ArgumentParser(description=__doc__,
                            formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    log("solomon_census: 2019 Census Basic Tables (Volume 2)")
    blob = http_get(URL, binary=True, timeout=600)
    assert isinstance(blob, bytes)
    check(blob[:5] == b"%PDF-", f"solomon_census: {URL} is not a PDF ({blob[:40]!r})")
    pages = page_texts(blob)
    log(f"  {len(blob):,} bytes, {len(pages)} pages")
    records = build(pages, fetch_wards(), load_units("SLB", "admin1"), load_units("SLB", "admin2"))
    log(f"  {len(records)} records: {summarise(records)}")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
