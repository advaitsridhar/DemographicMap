#!/usr/bin/env python3
"""Lebanon's cazas and governorates: residents by nationality, CAS LFHLCS 2018-19.

Lebanon has held no census since 1932. The nearest thing is the Central
Administration of Statistics' *Labour Force and Household Living Conditions
Survey 2018-2019* (LFHLCS, with the ILO), run in four quarterly rounds from
April 2018 to March 2019 and weighted to mid-2018 population estimates. Its
design (report, section 7.2) is a stratified two-stage sample of about 53,000
dwellings in about 2,700 ilots; the 26 cazas are its strata and estimation
domains, each allocated at least 68 ilots (a few slightly fewer after
fieldwork), and some 39,000 households answered. CAS publishes no sample size
per caza, but by design every caza holds hundreds of responding households,
far above the 100 respondents a survey unit needs here.

Its demography workbook (``LFHLCS_2018_2019_Demography.xls``) has, in
thousands of residents:

* Table HL.6A: residents by group of nationality (Lebanese, non-Lebanese) and
  caza;
* Table HL.5: residents by governorate, caza and sex.

**What is written.** Each drawn caza -- the boundary file draws the survey's
26 -- carries Lebanese against foreign nationals on the ethnicity field:
nationality, the only identity the survey tabulates, under the owner's
decision of 19 September 2026 that nationality may stand on that field. Each
drawn governorate carries the sum of the cazas the boundary file nests in it;
Keserwan-Jbeil, made a governorate in 2017, is two of the survey's Mount
Lebanon cazas. Nothing else: the survey's population, sex and ages are
estimates the map takes only from counts.

**Survey rules.** The basis says "survey estimate"; the file name ends in
``_survey.json``, so a count replaces it wherever one exists. CAS marks
estimates under 2,500 residents as having a relative standard error above
20%; a unit whose non-Lebanese estimate is under that is marked "low
precision". The universe is residents of residential dwellings: refugee
camps and their adjacent gatherings, informal settlements, army barracks and
work sites are outside it, so the survey undercounts the Palestinians, Syrians
and migrant workers who live there, and every note says so.

**Checks** (any failure stops the run): each caza's Lebanese and non-Lebanese
make its total; HL.6A's cazas make its Lebanon row; HL.5's caza totals are
HL.6A's and its governorates are the sums of their cazas; each of the 26 cazas
is drawn once, inside the drawn governorate its survey governorate became.

Usage:
    python -m scripts.fetch_census.lebanon_survey
"""

from __future__ import annotations

import argparse
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, gap, http_get, log, record, shares, write_json
from .west_asia_common import check, units

ISO3 = "LBN"
OUT = "lebanon_survey.json"
URL = "https://www.cas.gov.lb/wp-content/uploads/2026/06/LFHLCS_2018_2019_Demography.xls"
REPORT = ("https://www.cas.gov.lb/wp-content/uploads/2025/07/"
          "Labour-Force-and-Household-Living-Conditions-Survey-2018-2019.pdf")
YEAR = 2018
SOURCE = ("Central Administration of Statistics (Lebanon), Labour Force and Household Living "
          "Conditions Survey 2018-2019, Table HL.6A: residents by group of nationality and caza")
LICENCE = "Central Administration of Statistics (Lebanon), published survey tables"
BASIS = "survey estimate: nationality, residents of residential dwellings"
DECISION = "19 September 2026"
CITIZENS = "Lebanese"
OTHERS = "Foreign nationals"
# CAS: "Estimation below 2500 have a relative standard error above 20%".
RELIABLE = 2.5      # thousands
# Lebanese and non-Lebanese must make a caza's total within this (thousands).
ROUNDING = 0.01
# What no official source gives by caza or governorate. The survey's report
# (116 pages, probe 058fd4a) names no religion, confession or sect, and uses
# "language" only in its disability module ("communicating in one's own
# language"); and a survey's sex and age estimates are not counts.
SURVEY = ("the Central Administration of Statistics' Labour Force and Household Living "
          "Conditions Survey 2018-2019, the one official source with tables for every caza")
RELIGION_WHY = ("Lebanon has taken no census since 1932 and publishes no religious statistics: "
                f"{SURVEY}, asks no religion (its 116-page report names no religion, "
                "confession or sect).")
LANGUAGE_WHY = (f"Lebanon has taken no census since 1932, and {SURVEY} asks no language "
                "question (its 116-page report uses the word only in the disability module's "
                "'communicating in one's own language').")
AGE_SEX_WHY = ("Lebanon has taken no census since 1932; the only official figures of residents "
               f"by sex and age for a caza are survey estimates ({SURVEY}), which this map takes "
               "for compositions only, never for a count, a ratio or a median.")

# The survey's cazas as HL.6A names them -> the boundary file's labels.
CAZAS = {
    "Beirut": "Beirut", "Baabda": "Baabda", "Matn": "El Metn", "Chouf": "Chouf",
    "Aley": "Aley", "Keserwan": "Kesrouan", "Jbeil": "Jbail", "Tripoli": "Tripoli",
    "Koura": "Koura", "Zgharta": "Zgharta", "Batroun": "Batroun", "Akkar": "Akkar",
    "Bcharre": "Bcharre", "Minieh-Danniyeh": "Minieh-Dinnieh", "Zahleh": "Zahle",
    "West Beqaa": "West Bekaa", "Baalbek": "Baalbek", "Hermel": "Hermel",
    "Rachaya": "Rachaya", "Saida": "Saida", "Tyr": "Sour", "Jezzine": "Jezzine",
    "Nabatieh": "Nabatiye", "Bint Jbeil": "Bent Jbail", "Marjaayoun": "Marjaayoun",
    "Hasbaya": "Hasbaya",
}
# The survey's eight governorates -> the drawn governorates they became.
GOVERNORATES = {
    "Beirut": ["Beyrouth"], "Mount Lebanon": ["Mont-Liban", "Keserwan-Jbeil"],
    "North Lebanon": ["Liban-Nord"], "Akkar": ["Aakkâr"], "Bekaa": ["Béqaa"],
    "Baalbek-Hermel": ["Baalbek-Hermel"], "South Lebanon": ["Liban-Sud"],
    "Nabatieh": ["Nabatîyé"],
}


def number(cell: Any) -> float | None:
    try:
        return float(str(cell).strip())
    except (TypeError, ValueError):
        return None


def text(cell: Any) -> str:
    return " ".join(str(cell or "").split())


def table_hl6(rows: list[list[Any]]) -> tuple[dict[str, tuple[float, float]], float]:
    """Caza -> (Lebanese, non-Lebanese) in thousands, and Lebanon's total,
    from Table HL.6A (the sheet's first table)."""
    out: dict[str, tuple[float, float]] = {}
    total = None
    started = False
    for row in rows:
        label = text(row[0]) if row else ""
        if label.startswith("Table HL.6A"):
            started = True
            continue
        if not started:
            continue
        if label.startswith("Table HL.6B"):
            break
        figures = [number(c) for c in row[1:4]]
        if not label or any(f is None for f in figures):
            continue
        leb, non, tot = figures
        check(abs(leb + non - tot) <= ROUNDING,
              f"lebanon_survey: HL.6A {label}: {leb} + {non} is not {tot}")
        if label == "Total":
            total = tot
            break
        check(label in CAZAS, f"lebanon_survey: HL.6A names an unknown caza {label!r}")
        check(label not in out, f"lebanon_survey: HL.6A lists {label} twice")
        out[label] = (leb, non)
    check(total is not None, "lebanon_survey: HL.6A has no Lebanon row")
    check(set(out) == set(CAZAS), f"lebanon_survey: HL.6A's cazas are {sorted(out)}")
    made = sum(a + b for a, b in out.values())
    check(abs(made - total) <= ROUNDING * len(out),
          f"lebanon_survey: HL.6A's cazas make {made:.3f}, its Lebanon row {total:.3f}")
    return out, total


def table_hl5(rows: list[list[Any]]) -> dict[str, dict[str, float]]:
    """Survey governorate -> caza -> residents (thousands), from Table HL.5.
    Each governorate's 'Total' row must be the sum of its cazas."""
    out: dict[str, dict[str, float]] = {}
    gov = None
    for row in rows:
        if len(row) < 5:
            continue
        first, caza = text(row[0]), text(row[1])
        both = number(row[4])
        if first in GOVERNORATES:
            gov = first
            out[gov] = {}
        if gov is None or both is None or not caza:
            continue
        if caza == "Total":
            made = sum(out[gov].values())
            check(abs(made - both) <= ROUNDING * len(out[gov]),
                  f"lebanon_survey: HL.5 {gov}'s cazas make {made:.3f}, not {both:.3f}")
            gov = None
            continue
        out[gov][caza] = both
    check(set(out) == set(GOVERNORATES), f"lebanon_survey: HL.5's governorates are {sorted(out)}")
    return out


def note(name: str, leb: float, non: float, parts: list[str] | None = None) -> str:
    text_ = (
        f"Residents by nationality in the Central Administration of Statistics' Labour Force "
        f"and Household Living Conditions Survey 2018-2019 (Table HL.6A), weighted to mid-2018 "
        f"population estimates: an estimated {leb * 1000:,.0f} Lebanese and {non * 1000:,.0f} "
        f"non-Lebanese residents. Non-Lebanese is everyone without Lebanese citizenship, "
        f"whatever their nationality, the stateless included. The survey covers residential "
        f"dwellings only: refugee camps and their adjacent gatherings, informal settlements, "
        f"army barracks and work sites are left out, so the Palestinians, Syrians and migrant "
        f"workers living there are not in these figures. CAS publishes no sample size per "
        f"caza; each caza is one of the design's 26 strata, allocated at least 68 of its about "
        f"2,700 sample ilots (a few slightly fewer after fieldwork). Lebanon has held no census "
        f"since 1932. Nationality, not ethnicity: carried on this field under the owner's "
        f"decision of {DECISION}; 'Lebanese' is every Lebanese citizen, of whatever community.")
    if parts:
        text_ += " The sum of the survey's estimates for the cazas " + ", ".join(parts) + "."
    if non < RELIABLE:
        text_ += (f" Low precision: CAS marks estimates under {RELIABLE * 1000:,.0f} residents, "
                  f"as the non-Lebanese one is here, as having a relative standard error above "
                  f"20%.")
    return text_


def fields(name: str, leb: float, non: float, parts: list[str] | None = None
           ) -> dict[str, Any]:
    return {
        "ethnicity": shares({CITIZENS: leb * 1000, OTHERS: non * 1000}),
        "ethnicity_year": YEAR,
        "ethnicity_basis": BASIS,
        "ethnicity_note": note(name, leb, non, parts),
        "religion": gap(NOT_AVAILABLE, RELIGION_WHY),
        "language": gap(NOT_AVAILABLE, LANGUAGE_WHY),
        "median_age": gap(NOT_AVAILABLE, AGE_SEX_WHY),
        "sex_ratio": gap(NOT_AVAILABLE, AGE_SEX_WHY),
        "sources": [{"field": "ethnicity", "name": SOURCE, "url": URL, "year": YEAR,
                     "license": LICENCE},
                    {"field": "ethnicity (design)", "name": "LFHLCS 2018-2019 report, "
                     "section 7.2: sample design and sampling weights", "url": REPORT,
                     "year": YEAR, "license": LICENCE}],
    }


def build(hl6: list[list[Any]], hl5: list[list[Any]], admin1: list[dict[str, Any]],
          admin2: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cazas, total = table_hl6(hl6)
    govs = table_hl5(hl5)
    for gov, members in govs.items():
        for caza, people in members.items():
            check(caza in cazas, f"lebanon_survey: HL.5 names {caza!r}, which HL.6A does not")
            leb, non = cazas[caza]
            check(abs(leb + non - people) <= ROUNDING,
                  f"lebanon_survey: {caza} is {people} in HL.5 and {leb + non} in HL.6A")
    check(sorted(c for m in govs.values() for c in m) == sorted(cazas),
          "lebanon_survey: HL.5 and HL.6A list different cazas")
    labels1 = {u["id"]: u["name"] for u in admin1}
    drawn = {}
    for unit in admin2:
        drawn.setdefault(unit["name"], []).append(unit)
    check(sorted(drawn) == sorted(CAZAS.values()),
          f"lebanon_survey: drawn cazas {sorted(drawn)} are not the survey's")
    out: list[dict[str, Any]] = []
    by_region: dict[str, list[str]] = {}
    for gov, members in govs.items():
        for caza in members:
            found = drawn[CAZAS[caza]]
            check(len(found) == 1, f"lebanon_survey: {CAZAS[caza]} drawn {len(found)} times")
            unit = found[0]
            region = labels1.get(unit["parent"], "")
            check(region in GOVERNORATES[gov],
                  f"lebanon_survey: {caza} is drawn in {region!r}, not in {GOVERNORATES[gov]}")
            by_region.setdefault(region, []).append(caza)
            leb, non = cazas[caza]
            out.append(record(
                f"LBN-LFHLCS-{CAZAS[caza]}", unit["name"], level="admin2", parent=ISO3,
                country=ISO3, parent_name=region, match_by="shape_id", shape_id=unit["id"],
                aliases=[caza] if caza != unit["name"] else None,
                **fields(caza, leb, non)))
    drawn1 = {u["name"]: u for u in admin1}
    check(sorted(by_region) == sorted(drawn1),
          f"lebanon_survey: cazas fall in {sorted(by_region)}, drawn {sorted(drawn1)}")
    for region, members in sorted(by_region.items()):
        leb = sum(cazas[c][0] for c in members)
        non = sum(cazas[c][1] for c in members)
        out.append(record(
            f"LBN-LFHLCS-{region}", region, level="admin1", parent=ISO3, country=ISO3,
            match_by="shape_id", shape_id=drawn1[region]["id"],
            **fields(region, leb, non, parts=members if len(members) > 1 else None)))
    made = sum(sum(v) for v in cazas.values())
    log(f"  {len(cazas)} cazas, {len(by_region)} drawn governorates; {made:,.1f} thousand "
        f"residents (Lebanon row {total:,.1f})")
    for r in out:
        e = {s["group"]: s["pct"] for s in r["ethnicity"]}
        log(f"    {r['level']} {r['name']:16} Lebanese {e.get(CITIZENS, 0):5.1f}%"
            + ("  low precision" if "Low precision" in r["ethnicity_note"] else ""))
    return out


def main() -> int:
    argparse.ArgumentParser(description=__doc__,
                            formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    import xlrd
    blob = http_get(URL, binary=True, cache=False)
    book = xlrd.open_workbook(file_contents=blob)
    sheet = {name: [book.sheet_by_name(name).row_values(i)
                    for i in range(book.sheet_by_name(name).nrows)]
             for name in ("HL5", "HL6")}
    log(f"  {URL}: {len(blob):,} bytes")
    rows = build(sheet["HL6"], sheet["HL5"], units(ISO3, "admin1"), units(ISO3, "admin2"))
    write_json(PROCESSED / OUT, rows)
    log(f"  wrote {OUT} ({len(rows)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
