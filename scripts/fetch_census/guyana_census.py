#!/usr/bin/env python3
"""Guyana: the 2012 census's compositions and the 2022 census's count, by region.

All from the Bureau of Statistics:

* **2022, Preliminary Report, Appendix I.2**: each region's preliminary count
  -- the population reported, the institutional population and the estimated
  people of households never reached -- 878,674 in all. The population.
* **2012, Final Census Count, Table 1**: each region's men and women, the
  estimated no-contact persons included (746,955). The sex ratio.
* **2012, Compendium 2**: Table 2.3, each region's ethnic groups; Table 2.19,
  its religions; Table 2.13, its median age. The Bureau prorates the "not
  stated" and the no-contact persons over the stated answers, so each table
  makes the region's full count.

The report prints Table 2.3's wider figures cut at the column's edge and puts
the digits that did not fit on the line below ("126,37" / "8"); those are
put back, and each figure must then have whole thousands groups.

Checks, each of which stops the run: every table's regions make its Guyana
row, every row's regions make its total, Table 2.3's and Table 2.19's region
totals are the Final Count's, and the 2022 columns make each region's count.

The map's 26 sub-regions have nothing: every one of these publications, and
the 2012 Preliminary Report, tabulates by the ten regions (with Coastland,
Hinterland and the towns), none by sub-region.

Usage:
    python -m scripts.fetch_census.guyana_census
"""

from __future__ import annotations

import argparse
import io
import json
import re
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, gap, http_get, log, measure, record, shares, write_json
from .binding import fold

OUT = PROCESSED / "guyana_census.json"
SITE = PROCESSED.parent.parent / "site" / "data"
BASE = "https://statisticsguyana.gov.gy/wp-content/uploads/2019/10/"
PRELIMINARY_2022 = BASE + "Preliminary-Report-Guyana-National-Population-and-Housing-Census-2022.pdf"
FINAL_2012 = BASE + "Final_2012_Census_Count-1.pdf"
COMPENDIUM_2 = BASE + "Final_2012_Census_Compendium2.pdf"
SOURCE_2022 = ("Bureau of Statistics, Guyana, National Population and Housing Census 2022: "
               "Preliminary Report, Appendix I.2")
SOURCE_FINAL = "Bureau of Statistics, Guyana, 2012 Population and Housing Census: Final Results, Table 1"
SOURCE_C2 = ("Bureau of Statistics, Guyana, 2012 Population and Housing Census: Compendium 2, "
             "Population Composition")
TOTAL_2022 = 878_674
TOTAL_2012 = 746_955
REGIONS = ("Barima-Waini", "Pomeroon-Supenaam", "Essequibo Islands-West Demerara",
           "Demerara-Mahaica", "Mahaica-Berbice", "East Berbice-Corentyne", "Cuyuni-Mazaruni",
           "Potaro-Siparuni", "Upper Takutu-Upper Essequibo", "Upper Demerara-Berbice")
ETHNICITY = {"African / Black": "African", "Amerindian": "Amerindian", "Chinese": "Chinese",
             "East Indian": "East Indian", "Mixed": "Mixed", "Portuguese": "Portuguese",
             "White": "White", "Other": "Other"}
RELIGION = {"Anglican": "Anglican", "Methodist": "Methodist", "Pentecostal": "Pentecostal",
            "Roman Catholic": "Roman Catholic", "Jehovah Witness": "Jehovah's Witnesses",
            "Seventh Day Adventist": "Seventh-day Adventist", "Bahai": "Baha'i",
            "Muslim": "Muslim", "Hindu": "Hindu", "Rastafarian": "Rastafarian",
            "Other Christians": "Other Christian", "None": "No religion",
            "Other": "Other religion"}
FIGURE = re.compile(r"^\d{1,3}(?:,\d{3})*$")
CUT = re.compile(r"^\d{1,3}(?:,\d{3})*,\d{1,2}$")
SUBREGION_GAP = ("The Bureau of Statistics tabulates the 2012 and 2022 censuses by the ten "
                 "administrative regions (with Coastland, Hinterland and the towns): the 2012 "
                 "Final Count, Preliminary Report and Compendia 1 and 2 and the 2022 Preliminary "
                 "Report have no table by sub-region, so nothing is written for this one.")


def number(token: str) -> int:
    return int(token.replace(",", ""))


def present(counts: dict[str, float]) -> list[dict]:
    return shares({k: v for k, v in counts.items() if v})


def between(lines: list[str], first: str, stop: str) -> list[str]:
    start = next((i for i, l in enumerate(lines)
                  if l.startswith(first) and not re.search(r"\.{4,}", l)), None)
    if start is None:
        raise SystemExit(f"guyana_census: no {first!r}")
    end = next((i for i, l in enumerate(lines[start + 1:], start + 1) if l.startswith(stop)),
               len(lines))
    return lines[start + 1:end]


def check_grid(rows: dict[str, list[int]], what: str, totals: list[int] | None = None) -> None:
    """Each row's ten regions make its total, the rows make the Total row."""
    whole = rows.get("Total")
    if whole is None:
        raise SystemExit(f"guyana_census: {what} has no Total row")
    for label, figures in rows.items():
        if len(figures) != 11 or sum(figures[:10]) != figures[10]:
            raise SystemExit(f"guyana_census: {what}'s {label}: {figures}")
    parts = [r for label, r in rows.items() if label != "Total"]
    for j in range(11):
        if sum(r[j] for r in parts) != whole[j]:
            raise SystemExit(f"guyana_census: {what}'s column {j + 1} does not make its total")
    if whole[10] != TOTAL_2012 or (totals and whole[:10] != totals):
        raise SystemExit(f"guyana_census: {what}'s regions are {whole}")


def table_2_3(lines: list[str]) -> dict[str, list[int]]:
    """{ethnic group: 10 regions + total} from Table 2.3, its cut figures made whole."""
    rows: dict[str, list[int]] = {}
    pending: tuple[str, list[str]] | None = None

    def close(label: str, tokens: list[str], rest: list[str]) -> None:
        cut = [i for i, t in enumerate(tokens) if CUT.match(t)]
        if len(rest) != len(cut):
            raise SystemExit(f"guyana_census: Table 2.3's {label}: {len(cut)} figures cut, "
                             f"{len(rest)} ends below them")
        tokens = list(tokens)
        for i, tail in zip(cut, rest):
            tokens[i] += tail
            if not FIGURE.match(tokens[i]):
                raise SystemExit(f"guyana_census: Table 2.3's {label}: {tokens[i]} is no figure")
        rows[label] = [number(t) for t in tokens]

    for line in lines:
        tokens = line.split()
        if len(tokens) > 11 and all(FIGURE.match(t) or CUT.match(t) for t in tokens[-11:]):
            if pending:
                close(pending[0], pending[1], [])
            pending = (" ".join(tokens[:-11]), tokens[-11:])
            continue
        if pending is None:
            continue
        words = [t for t in tokens if not t.isdigit()]
        digits = [t for t in tokens if t.isdigit()]
        label = " ".join([pending[0]] + words).strip()
        close(label, pending[1], digits)
        pending = None
    if pending:
        close(pending[0], pending[1], [])
    unknown = set(rows) - set(ETHNICITY) - {"Total"}
    if unknown:
        raise SystemExit(f"guyana_census: Table 2.3 groups this does not read: {sorted(unknown)}")
    return rows


def table_2_19(lines: list[str]) -> dict[str, list[int]]:
    """{religion: 10 regions + total} from Table 2.19; a label may wrap below its figures."""
    rows: list[list] = []
    for line in lines:
        tokens = line.split()
        if len(tokens) > 11 and all(FIGURE.match(t) for t in tokens[-11:]):
            rows.append([" ".join(tokens[:-11]), [number(t) for t in tokens[-11:]]])
            if rows[-1][0] == "Total":
                break
        elif rows and tokens and not any(ch.isdigit() for ch in line):
            rows[-1][0] = f"{rows[-1][0]} {line.strip()}"
    out = {label: figures for label, figures in rows}
    unknown = set(out) - set(RELIGION) - {"Total"}
    if unknown:
        raise SystemExit(f"guyana_census: Table 2.19 religions this does not read: "
                         f"{sorted(unknown)}")
    return out


def table_2_13(lines: list[str]) -> dict[int, float]:
    """{region number: 2012 median age} from Table 2.13 ("Region 18.57 ... 17.48" / "1")."""
    out: dict[int, float] = {}
    for line, after in zip(lines, lines[1:] + [""]):
        m = re.match(r"^Region((?:\s+\d+\.\d+){9})$", line.strip())
        if m and re.fullmatch(r"\d{1,2}", after.strip()):
            out[int(after)] = float(m[1].split()[-1])
    if sorted(out) != list(range(1, 11)):
        raise SystemExit(f"guyana_census: Table 2.13 has regions {sorted(out)}")
    return out


def region_rows(lines: list[str], width: int, total_label: str) -> dict[int, list[int]]:
    """{region number: figures} from lines "Region N f1 ... fwidth", and 0 for the total."""
    out: dict[int, list[int]] = {}
    for line in lines:
        tokens = line.split()
        if len(tokens) != width + (1 if tokens and tokens[0] == total_label else 2):
            continue
        if not all(FIGURE.match(t) for t in tokens[-width:]):
            continue
        if tokens[0] == "Region" and tokens[1].isdigit():
            out[int(tokens[1])] = [number(t) for t in tokens[-width:]]
        elif tokens[0] == total_label:
            out[0] = [number(t) for t in tokens[-width:]]
    if sorted(out) != list(range(0, 11)):
        raise SystemExit(f"guyana_census: a region table has {sorted(out)}")
    return out


def final_count(lines: list[str]) -> dict[int, tuple[int, int, int]]:
    """{region: (men, women, total)} from the Final Count's Table 1 (last three columns)."""
    rows = region_rows(lines, 12, "Total")
    out = {r: tuple(v[-3:]) for r, v in rows.items()}
    for r, (men, women, total) in out.items():
        if men + women != total:
            raise SystemExit(f"guyana_census: Final Count region {r}: {men} + {women} != {total}")
    if out[0][2] != TOTAL_2012 or sum(out[r][2] for r in range(1, 11)) != TOTAL_2012:
        raise SystemExit("guyana_census: the Final Count's regions do not make 746,955")
    return out


def count_2022(lines: list[str]) -> dict[int, int]:
    """{region: 2022 preliminary count} from Appendix I.2."""
    rows = region_rows(lines, 4, "Guyana")
    for r, (reported, institutional, no_contact, total) in rows.items():
        if reported + institutional + no_contact != total:
            raise SystemExit(f"guyana_census: Appendix I.2 region {r} does not add up")
    if rows[0][3] != TOTAL_2022 or sum(rows[r][3] for r in range(1, 11)) != TOTAL_2022:
        raise SystemExit("guyana_census: Appendix I.2's regions do not make 878,674")
    return {r: v[3] for r, v in rows.items() if r}


def pdf_lines(url: str) -> list[str]:
    import pdfplumber
    out: list[str] = []
    with pdfplumber.open(io.BytesIO(http_get(url, binary=True, cache=False))) as pdf:
        for page in pdf.pages:
            out += (page.extract_text() or "").splitlines()
    return out


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    final = final_count(between(pdf_lines(FINAL_2012), "Table 1: Regional Distribution",
                                "Table 2"))
    compendium = pdf_lines(COMPENDIUM_2)
    ethnic = table_2_3(between(compendium, "Table 2.3:", "Source:"))
    religion = table_2_19(between(compendium, "Table 2.19:", "Note:"))
    totals = [final[r][2] for r in range(1, 11)]
    check_grid(ethnic, "Table 2.3", totals)
    check_grid(religion, "Table 2.19", totals)
    median = table_2_13(between(compendium, "Table 2.13:", "Source:"))
    recent = count_2022(between(pdf_lines(PRELIMINARY_2022), "Appendix-I.2", "Source:"))
    log(f"  2012: ten regions making {TOTAL_2012:,} in Tables 2.3 and 2.19 and the Final "
        f"Count; 2022: making {TOTAL_2022:,}")

    admin1 = json.loads((SITE / "admin1" / "GUY.units.json").read_text())
    shapes = {fold(u["name"]): u for u in admin1}
    records = []
    for number_, name in enumerate(REGIONS, start=1):
        shape = shapes.get(fold(name))
        if shape is None:
            raise SystemExit(f"guyana_census: region {name} has no polygon")
        men, women, _ = final[number_]
        j = number_ - 1
        records.append(record(
            f"GUY-BOS-{number_}", shape["name"], level="admin1", parent="GUY", country="GUY",
            match_by="shape_id", shape_id=shape["id"],
            population=measure(recent[number_], year=2022, source=SOURCE_2022),
            population_note=("The 2022 census's preliminary count: the population reported, "
                             "the institutional population and the estimated people of "
                             "households never reached."),
            sex_ratio=measure(round(1000 * men / women), unit="males_per_1000_females",
                              year=2012, source=SOURCE_FINAL),
            sex_ratio_note="Men per thousand women, 2012, no-contact persons included.",
            median_age=measure(round(median[number_], 1), unit="years", year=2012,
                               source=f"{SOURCE_C2}, Table 2.13"),
            median_age_note="The Bureau's median age of the region's 2012 population.",
            ethnicity=present({ETHNICITY[g]: v[j] for g, v in ethnic.items() if g != "Total"}),
            ethnicity_year=2012,
            ethnicity_note=("Table 2.3: ethnic group, with the 321 not stated and the 16,331 "
                            "no-contact persons prorated over the groups by the Bureau."),
            religion=present({RELIGION[g]: v[j] for g, v in religion.items() if g != "Total"}),
            religion_year=2012,
            religion_note=("Table 2.19: religious affiliation, with the 363 not stated, the "
                           "no-contact persons and the institutional population prorated by "
                           "the Bureau."),
            sources=[{"field": "population", "name": SOURCE_2022, "url": PRELIMINARY_2022,
                      "year": 2022},
                     {"field": "sex_ratio", "name": SOURCE_FINAL, "url": FINAL_2012,
                      "year": 2012},
                     {"field": "median_age/ethnicity/religion", "name": SOURCE_C2,
                      "url": COMPENDIUM_2, "year": 2012}]))
    admin2 = json.loads((SITE / "admin2" / "GUY.units.json").read_text())
    for shape in admin2:
        records.append(record(
            f"GUY-BOS-sub-{shape['id']}", shape["name"], level="admin2", parent="GUY",
            country="GUY", match_by="shape_id", shape_id=shape["id"],
            **{f: gap(NOT_AVAILABLE, SUBREGION_GAP)
               for f in ("population", "median_age", "sex_ratio", "religion", "ethnicity")}))
    write_json(OUT, records)
    log(f"  wrote {OUT.name}: {len(REGIONS)} regions, {len(admin2)} sub-regions with the "
        "reason they have nothing")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
