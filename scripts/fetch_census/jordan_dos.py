#!/usr/bin/env python3
"""Jordan's twelve governorates: people and sex (end of 2025), age and nationality (2015 census).

Two publications of the Department of Statistics (DoS) are read:

* the population estimates workbook (``PopulationEstimates.xlsx``), whose
  Table 2.2 gives every governorate's estimated men, women and total at the
  end of 2025, and whose Table 2.1 gives the kingdom's total for the same
  year, which the governorates must make;
* three tables of the Population and Housing Census 2015, PDFs of the DoS
  data bank: Table 3.1 (the population inside Jordan by nationality --
  Jordanian or not -- sex and administrative division, beside the Jordanians
  abroad, whom its total also counts and who are left out here), Table 3.4 (the same
  people by age group, sex and governorate) and Table 8.1 (the non-Jordanians
  by country of nationality, sex and governorate).

**What is written** on each governorate the map draws: the end-2025 estimate
of its population and its males per 100 females; the median age of everyone
the 2015 census counted in it, interpolated within the census's age groups
(under 1, 1-4, 5-9 ... 75-79, 80 and over); and its people by nationality on
the ethnicity field (``ethnicity_basis`` "nationality", the owner's decision
of 19 September 2026: the census asks nationality and no ethnic group) --
Jordanians, the large foreign nationalities by name, the rest by region.

**Not the second level.** Table 2.4 of the estimates gives every liwa
(district) and qada (sub-district), but the boundary file's Jordanian
second-level shapes are not the places their labels name: the shape
labelled "Wastiyyeh" holds Irbid city, the one labelled "Jerash" holds
Ajloun city as well as Jerash, "Ayy" holds Safi, "Faqqu" holds al-Qasr.
No figure is bound to them.

**Checks** (any failure stops the run and nothing is written): in the
estimates, each governorate's men and women make its total and the twelve
make the kingdom's total for the same year in Table 2.1; in the census, each
governorate's Jordanians and others make its people, its men and women make
each total, the governorates make the kingdom on every column, the age
groups make the governorate's people, and the nationalities of Table 8.1
make the non-Jordanians of Table 3.1 governorate by governorate; every
drawn governorate is bound to one DoS governorate and none twice.

Usage:
    python -m scripts.fetch_census.jordan_dos
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from ._shared import (NOT_AVAILABLE, NOT_COLLECTED, PROCESSED, collection_gap, gap, log, measure,
                      record, shares, write_json)
from .west_asia_common import check, key, median_age, sex_ratio, units, workbook

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from probe_pdf import PAGE_BREAK, fetch_blob, laid_out  # noqa: E402

ISO3 = "JOR"
OUT = "jordan_dos.json"
ESTIMATES = ("https://dosweb.dos.gov.jo/databank/Population/Population_Estimares/"
             "PopulationEstimates.xlsx")
CENSUS = "https://dosweb.dos.gov.jo/DataBank/Census2015/"
TOTALS = CENSUS + "Persons/Persons_3.1.pdf"
AGES = CENSUS + "Persons/Persons_3.4.pdf"
NATIONALITIES = CENSUS + "Non-Jordanians/Non-jordanian_8.1.pdf"
QUESTIONNAIRE = "https://dosweb.dos.gov.jo/DataBank/census2015/Questionare_en.pdf"
CENSUS_YEAR = 2015
SOURCE_ESTIMATES = ("Department of Statistics (Jordan), Estimated Population of the Kingdom "
                    "by Governorate and Sex, at end of {year} (Table 2.2)")
SOURCE_CENSUS = ("Department of Statistics (Jordan), Population and Housing Census 2015, "
                 "Tables 3.1, 3.4 and 8.1")
LICENCE = "Department of Statistics (Jordan), published statistics"
DECISION = "19 September 2026"
NO_RELIGION = (
    "Jordan's 2015 census asked each person's religion (its household form puts it beside "
    "sex and nationality: " + QUESTIONNAIRE + "), but the Department of Statistics publishes "
    "no religion table from it: the census's person tables (3.1 to 3.19, by population "
    "category, age, households, residence, health insurance and marriage) and its other "
    "series carry none, so no governorate's religion is published.")
NO_LANGUAGE = (
    "Jordan's 2015 census does not ask language: its questionnaire (" + QUESTIONNAIRE + ") "
    "has no language or mother-tongue question, and no census table carries one.")
# The DoS's governorate names, as its tables spell them, -> the map's labels.
GOVERNORATES = {
    "Amman": "Amman", "Capital": "Amman", "Balqa": "Balqa", "Al-Balqa": "Balqa",
    "Zarqa": "Zarqa", "Madaba": "Madaba", "Irbid": "Irbid", "Mafraq": "Mafraq",
    "Jarash": "Jerash", "Jerash": "Jerash", "Ajlun": "Ajloun", "Ajloun": "Ajloun",
    "Karak": "Karak", "Tafiela": "Tafilah", "Tafileh": "Tafilah", "Tafila": "Tafilah",
    "Tafilah": "Tafilah", "Tafielah": "Tafilah", "Ma'an": "Ma'an", "Maan": "Ma'an",
    "Aqaba": "Aqaba",
}
BY_KEY = {key(k): v for k, v in GOVERNORATES.items()}
KINGDOM = key("Jordan")
ARABIC = re.compile(r"[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]")
# Table 8.1's sections, each with the label its unnamed countries take.
SECTIONS = (
    (re.compile(r"^Arab Asian"), "Other Arab nationalities"),
    (re.compile(r"^Non-Arab Asian"), "Asian nationalities"),
    (re.compile(r"^Arab African"), "Other Arab nationalities"),
    (re.compile(r"^Non-Arab African"), "African nationalities"),
    (re.compile(r"Europe"), "European nationalities"),
    (re.compile(r"^North America"), "North American nationalities"),
    (re.compile(r"^(Middle|Central|South|Latin) America|Caribbean"), "Other nationalities"),
    (re.compile(r"^Oceania"), "Other nationalities"),
    (re.compile(r"^Others?$"), "Other nationalities"),
)
# Nationalities written by name; every other country takes its section's label.
NAMED = {
    "Syria": "Syrian", "Egypt": "Egyptian", "Palestine": "Palestinian", "Iraq": "Iraqi",
    "Yemen": "Yemeni", "Libya": "Libyan", "Sudan": "Sudanese", "Saudi Arabia": "Saudi",
    "Lebanon": "Lebanese", "Philippines": "Filipino", "Bangladesh": "Bangladeshi",
    "India": "Indian", "Pakistan": "Pakistani", "Sri Lanka": "Sri Lankan",
    "Indonesia": "Indonesian",
}
AGE_ROW = re.compile(r"^(<1|\d+-\d+|\d+\+)\s+((?:\d+\s+){11}\d+)(?:\s|$)")
TOTAL_ROW = re.compile(r"^Total\s+((?:\d+\s+){11}\d+)(?:\s|$)")
COUNTRY_ROW = re.compile(r"^([A-Za-z][^0-9]*?)\s+((?:\d+\s+){8}\d+)(?:\s|$)")


def english(line: str) -> str:
    """The part of a laid-out line before its Arabic, stripped."""
    m = ARABIC.search(line)
    return (line[:m.start()] if m else line).strip()


# Every label without figures the readers met, to name in a failure.
SEEN: set[str] = set()


def heading(line: str) -> str | None:
    """'kingdom' or the map's governorate if the line is a governorate's heading."""
    if re.search(r"\d", line):
        return None
    if english(line) and ARABIC.search(line):
        SEEN.add(english(line)[:40])
    k = key(english(line))
    if k == KINGDOM:
        return "kingdom"
    return BY_KEY.get(k)


def numbers(text: str) -> list[int]:
    return [int(n) for n in text.split()]


def triples_add_up(cells: list[int], where: str) -> None:
    for i in range(0, len(cells), 3):
        f, m, t = cells[i:i + 3]
        check(f + m == t, f"jordan_dos: {where}: {f:,} women and {m:,} men are not {t:,}")


def read_estimates(sheets: dict[str, list[list[Any]]]) -> tuple[int, dict[str, dict[str, int]]]:
    """(year, governorate -> men, women, total) from Table 2.2; checked on Table 2.1."""
    out: dict[str, dict[str, int]] = {}
    year = None
    kingdom: dict[int, int] = {}
    for rows in sheets.values():
        inside = False
        for row in rows:
            texts = [str(c) for c in row if isinstance(c, str)]
            title = next((t for t in texts if re.match(r"\s*Table 2\.\d", t)), None)
            if title:
                inside = bool(re.match(r"\s*Table 2\.2\b", title))
                if inside:
                    m = re.search(r"(20\d\d)", title)
                    year = int(m.group(1)) if m else year
                continue
            nums = [c for c in row[1:] if isinstance(c, (int, float)) and not isinstance(c, bool)]
            # Table 2.1: a year (perhaps footnoted, "(6)2015"), then men, women, total.
            first = row[0] if row else None
            m = re.fullmatch(r"(?:\(\d\))?(\d{4})(?:\.0)?", str(first).strip()) \
                if first is not None else None
            if m and len(nums) >= 3 and round(nums[0]) + round(nums[1]) == round(nums[2]):
                kingdom[int(m.group(1))] = round(nums[2])
            if not inside:
                continue
            name = next((t for t in texts[1:] if key(t) in BY_KEY or key(t) == key("Total")),
                        None)
            if name is None or len(nums) < 3:
                continue
            men, women, total = (round(v) for v in nums[:3])
            check(men + women == total,
                  f"jordan_dos: Table 2.2 {name}: {men:,} + {women:,} is not {total:,}")
            if key(name) == key("Total"):
                out["total"] = {"men": men, "women": women, "total": total}
                inside = False
                continue
            gov = BY_KEY[key(name)]
            check(gov not in out, f"jordan_dos: Table 2.2 {gov} twice")
            out[gov] = {"men": men, "women": women, "total": total}
    govs = sorted(g for g in out if g != "total")
    check(len(govs) == 12, f"jordan_dos: Table 2.2 governorates {govs}")
    check("total" in out, "jordan_dos: Table 2.2 has no total row")
    made = sum(out[g]["total"] for g in govs)
    check(made == out["total"]["total"],
          f"jordan_dos: Table 2.2 governorates make {made:,}, not {out['total']['total']:,}")
    if year is None:
        year = next((y for y, v in kingdom.items() if v == made), None)
    check(year is not None, "jordan_dos: Table 2.2 names no year")
    check(kingdom.get(year) == made,
          f"jordan_dos: Table 2.1 gives the kingdom {kingdom.get(year)} at end of {year}, "
          f"the governorates make {made:,}")
    return year, {g: out[g] for g in govs}


def read_totals(text: str) -> dict[str, list[int]]:
    """Governorate (and 'kingdom') -> Table 3.1's twelve totals.

    Jordanians abroad, non-Jordanians and Jordanians inside Jordan, and all
    three together, each as women, men, total. Only the first Total after a
    governorate's heading is the governorate's; its districts' blocks follow
    under their own headings.
    """
    out: dict[str, list[int]] = {}
    current = None
    for line in text.splitlines():
        line = line.strip()
        gov = heading(line)
        if gov:
            current = gov
            continue
        if re.search(r"District|Sub-District", english(line)):
            current = None
            continue
        m = TOTAL_ROW.match(line)
        if m and current:
            cells = numbers(m.group(1))
            triples_add_up(cells, f"Table 3.1 {current}")
            check(cells[2] + cells[5] + cells[8] == cells[11],
                  f"jordan_dos: Table 3.1 {current}: Jordanians abroad, non-Jordanians and "
                  f"Jordanians are not the total")
            check(current not in out, f"jordan_dos: Table 3.1 {current} twice")
            out[current] = cells
            current = None
    return out


def read_ages(text: str) -> dict[str, dict[str, Any]]:
    """Governorate (and 'kingdom') -> everyone inside Jordan by age group (Table 3.4).

    Inside Jordan is the non-Jordanians and Jordanians columns together; the
    table's total column also counts Jordanians abroad, who are left out.
    """
    out: dict[str, dict[str, Any]] = {}
    current = None
    groups: list[tuple[int, int | None, float]] = []
    for line in text.splitlines():
        line = line.strip()
        gov = heading(line)
        if gov:
            current, groups = gov, []
            continue
        if current is None:
            continue
        m = AGE_ROW.match(line)
        if m:
            label, cells = m.group(1), numbers(m.group(2))
            triples_add_up(cells, f"Table 3.4 {current} {label}")
            if label == "<1":
                lo, hi = 0, 0
            elif label.endswith("+"):
                lo, hi = int(label[:-1]), None
            else:
                lo, hi = (int(v) for v in label.split("-"))
            groups.append((lo, hi, cells[5] + cells[8]))
            continue
        m = TOTAL_ROW.match(line)
        if m:
            cells = numbers(m.group(1))
            made = sum(n for _a, _b, n in groups)
            inside = cells[5] + cells[8]
            check(made == inside, f"jordan_dos: Table 3.4 {current}: age groups make "
                                  f"{made:,}, not {inside:,}")
            check(current not in out, f"jordan_dos: Table 3.4 {current} twice")
            out[current] = {"groups": sorted(groups), "total": inside, "row": cells}
            current = None
            continue
        # A governorate's urban and rural blocks ("Amman - Urban") end its own;
        # the column heading every page repeats ("Urban/ Rural & ...") does not.
        if not re.search(r"\d", line) and re.search(r"\s-\s*(Urban|Rural)\b", english(line)):
            current = None
    return out


def read_nationalities(text: str) -> dict[str, dict[str, Any]]:
    """Governorate (and 'kingdom') -> non-Jordanians by the map's label (Table 8.1).

    Every Total row must be either its section's countries (a subtotal) or
    all the governorate's countries so far (its grand total, which the table
    does not print for every governorate) -- or the kingdom's, which the
    table prints again at its very end; the governorate's countries are
    checked against Table 3.1's non-Jordanians afterwards.
    """
    out: dict[str, dict[str, Any]] = {}
    current, label = None, None
    section_sum = 0
    unread: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        gov = heading(line)
        if gov:
            check(gov not in out, f"jordan_dos: Table 8.1 {gov} twice")
            current, label, section_sum = gov, None, 0
            out[current] = {"counts": defaultdict(int), "countries": 0, "subtotals": 0}
            continue
        if current is None:
            continue
        name = english(line)
        if name and not re.search(r"\d", line):
            if ARABIC.search(line):
                hit = next((lab for pat, lab in SECTIONS if pat.search(name)), None)
                if hit:
                    label, section_sum = hit, 0
                    continue
                check("Countr" not in name,
                      f"jordan_dos: Table 8.1 {current}: unknown section {name!r}")
            unread.append(name)
            continue
        m = COUNTRY_ROW.match(line)
        if not m:
            continue
        country, cells = m.group(1).strip(" -"), numbers(m.group(2))
        triples_add_up(cells, f"Table 8.1 {current} {country}")
        check(cells[2] + cells[5] == cells[8],
              f"jordan_dos: Table 8.1 {current} {country}: rural and urban are not the total")
        if country == "Total":
            # The table closes on the kingdom's total again, after Aqaba's block.
            kingdom = out["kingdom"]["countries"] if "kingdom" in out and current != "kingdom" \
                else None
            check(cells[8] in (section_sum, out[current]["countries"], kingdom),
                  f"jordan_dos: Table 8.1 {current}: a Total of {cells[8]:,} is neither its "
                  f"section's {section_sum:,} nor the governorate's {out[current]['countries']:,}")
            out[current]["subtotals"] += 1
            continue
        check(label is not None, f"jordan_dos: Table 8.1 {current}: {country} before any "
                                 f"section")
        out[current]["counts"][NAMED.get(country, label)] += cells[8]
        out[current]["countries"] += cells[8]
        section_sum += cells[8]
    for gov, entry in out.items():
        check(entry["subtotals"] >= 1, f"jordan_dos: Table 8.1 {gov}: no Total row at all")
    if unread:
        log(f"  Table 8.1 lines read as no row: {sorted(set(unread))[:20]}")
    return out


def check_kingdom(totals: dict[str, list[int]], ages: dict[str, dict[str, Any]],
                  nats: dict[str, dict[str, Any]]) -> list[str]:
    govs = sorted(g for g in totals if g != "kingdom")
    found = [sorted(totals), sorted(ages), sorted(nats)]
    if any(len(f) != 13 for f in found):
        log(f"  governorates found: Table 3.1 {found[0]}; 3.4 {found[1]}; 8.1 {found[2]}")
        log(f"  labels without figures: {sorted(SEEN)[:150]}")
    check(len(govs) == 12, f"jordan_dos: Table 3.1 governorates {govs}")
    check("kingdom" in totals, "jordan_dos: Table 3.1 has no kingdom row")
    for i in range(12):
        made = sum(totals[g][i] for g in govs)
        check(made == totals["kingdom"][i],
              f"jordan_dos: Table 3.1 column {i + 1}: governorates make {made:,}, the "
              f"kingdom {totals['kingdom'][i]:,}")
    check(sorted(g for g in ages if g != "kingdom") == govs,
          f"jordan_dos: Table 3.4 governorates {sorted(ages)}")
    check(sorted(g for g in nats if g != "kingdom") == govs,
          f"jordan_dos: Table 8.1 governorates {sorted(nats)}")
    for g in govs + ["kingdom"]:
        if g in ages:
            check(ages[g]["row"] == totals[g],
                  f"jordan_dos: {g}: Table 3.4's total row {ages[g]['row']} is not Table "
                  f"3.1's {totals[g]}")
        if g in nats:
            check(nats[g]["countries"] == totals[g][5],
                  f"jordan_dos: {g}: Table 8.1's countries make {nats[g]['countries']:,} "
                  f"non-Jordanians, Table 3.1 {totals[g][5]:,}")
    return govs


def build(year: int, estimates: dict[str, dict[str, int]], totals: dict[str, list[int]],
          ages: dict[str, dict[str, Any]], nats: dict[str, dict[str, Any]],
          admin1: list[dict[str, Any]]) -> list[dict[str, Any]]:
    govs = check_kingdom(totals, ages, nats)
    check(sorted(estimates) == govs,
          f"jordan_dos: the estimates' governorates {sorted(estimates)} are not the census's")
    bound: dict[str, str] = {}
    for unit in admin1:
        gov = BY_KEY.get(key(unit["name"]))
        check(gov is not None, f"jordan_dos: no DoS governorate for {unit['name']}")
        check(gov not in bound.values(), f"jordan_dos: {gov} bound twice")
        bound[unit["id"]] = gov
    check(sorted(bound.values()) == govs, f"jordan_dos: drawn governorates {sorted(bound)}")
    source_estimates = SOURCE_ESTIMATES.format(year=year)
    sources = [
        {"field": "population/sex_ratio", "name": source_estimates, "url": ESTIMATES,
         "year": year, "license": LICENCE},
        {"field": "median_age/ethnicity", "name": SOURCE_CENSUS, "url": TOTALS,
         "year": CENSUS_YEAR, "license": LICENCE},
    ]
    rows: list[dict[str, Any]] = []
    for unit in admin1:
        gov = bound[unit["id"]]
        est = estimates[gov]
        population = measure(est["total"], year=year, source=source_estimates)
        population["note"] = (f"The DoS's estimate for the end of {year}: {est['men']:,} men "
                              f"and {est['women']:,} women.")
        cells = totals[gov]
        everyone, jordanians = cells[5] + cells[8], cells[8]
        counts = {"Jordanian": jordanians}
        for lab, n in nats[gov]["counts"].items():
            if n:
                counts[lab] = counts.get(lab, 0) + n
        check(sum(counts.values()) == everyone,
              f"jordan_dos: {gov}: nationalities make {sum(counts.values()):,}, not "
              f"{everyone:,}")
        rows.append(record(
            f"JOR-DOS-{gov}", unit["name"], level="admin1", parent=ISO3, country=ISO3,
            match_by="shape_id", shape_id=unit["id"],
            population=population,
            sex_ratio=sex_ratio(est["men"], est["women"], year=year, source=source_estimates),
            sex_ratio_note=(f"Males per 100 females in the DoS's estimate for the end of "
                            f"{year}: {est['men']:,} men and {est['women']:,} women."),
            median_age=median_age(ages[gov]["groups"], year=CENSUS_YEAR, source=SOURCE_CENSUS),
            median_age_note=(
                f"Median age of everyone the 2015 census counted inside Jordan in the "
                f"governorate, Jordanians and others ({everyone:,} people; Jordanians "
                f"abroad left out), interpolated within the "
                f"census's age groups (under 1, 1-4, 5-9 and so on to 80 and over; Table 3.4)."),
            ethnicity=shares(counts, total=everyone),
            ethnicity_year=CENSUS_YEAR, ethnicity_basis="nationality",
            ethnicity_note=(
                "Nationality, not ethnicity: the 2015 census records each person's "
                "nationality and asks no ethnic question. Carried on this field under the "
                f"owner's decision of {DECISION}. Everyone counted inside Jordan "
                f"({everyone:,} people; Jordanians abroad left out): Jordanians from Table "
                "3.1, everyone else by country of nationality from Table 8.1, the largest by "
                "name and the rest by region. 'Palestinian' is Palestinian nationality "
                "(chiefly people from Gaza), not Jordanians of Palestinian origin, who are "
                "Jordanian."),
            religion=gap(NOT_AVAILABLE, NO_RELIGION),
            language=collection_gap(ISO3, "language") or gap(NOT_COLLECTED, NO_LANGUAGE),
            sources=sources))
    return rows


def pdf_text(url: str) -> str:
    blob = fetch_blob(url)
    log(f"  {url}: {len(blob):,} bytes")
    return laid_out(blob).replace(PAGE_BREAK, "\n")


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    year, estimates = read_estimates(workbook(ESTIMATES))
    totals = read_totals(pdf_text(TOTALS))
    ages = read_ages(pdf_text(AGES))
    nats = read_nationalities(pdf_text(NATIONALITIES))
    rows = build(year, estimates, totals, ages, nats, units(ISO3, "admin1"))
    log(f"  estimates end of {year}: {sum(e['total'] for e in estimates.values()):,}; "
        f"census 2015: {totals['kingdom'][5] + totals['kingdom'][8]:,} inside Jordan, "
        f"{totals['kingdom'][2]:,} Jordanians abroad")
    write_json(PROCESSED / OUT, rows)
    log(f"  wrote {OUT} ({len(rows)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
