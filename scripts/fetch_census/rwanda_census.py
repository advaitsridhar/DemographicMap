#!/usr/bin/env python3
"""Rwanda: the 2022 census by province and district -- head count, sex ratio, median
age, religion, and nationality by province.

The National Institute of Statistics of Rwanda (NISR) took the Fifth Population and
Housing Census (RPHC5) in August 2022 and publishes its tables as workbooks and
reports. Three are read here:

* *Main Indicators* (workbook): Table 1, the resident population by sex, province
  and district; Table 6, the population by nationality (Rwandan or foreign) and
  province.
* *Thematic Report: Population size, structure and spatial distribution*
  (workbook): Table 4.3, the median age by province, and Table 4.4, the median age
  by district -- whole years, for men, women and both.
* The 30 *District Profiles* (PDF, September 2023): each prints its district's
  resident population by religious affiliation, in counts, and by nationality
  (Table 2.1, Rwandan or foreign, by sector, with the district's own row).

**What is written.** For each district and province: the population and men per
1,000 women (Table 1), the median age of both sexes (Tables 4.3 and 4.4, as the
Institute prints it, in whole years), and religion (the district's profile; a
province's is its districts' counts added up). Nationality goes on the ethnicity
field (``ethnicity_basis``: nationality), since the census asks no ethnicity:
Table 6's for each province, the profile's Table 2.1 for each district. The
census's only language table (Main Indicators Table 8) is literacy, the
languages people aged 15 and over read and write, and not a language
composition, so every unit says so (LANGUAGE). OCHA's district table for Rwanda
projects the 2012 census to 2023 and gives way to these counts
(SUPERSEDED_ROWS); its medians, a projection too, only fill, and these stand in
front of them.

**Checks.** Each row's men and women make it; the districts make their province and
the provinces the country; Rwandans and foreigners make each province; a profile's
religions make its district's count in Table 1, and so do its Rwandans and
foreigners, whose printed shares they must give; a province's districts' Rwandans
and foreigners must make Table 6's, or none of its districts' are written.

Usage:
    python -m scripts.fetch_census.rwanda_census
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
from typing import Any

from ._shared import (NOT_AVAILABLE, PROCESSED, dated, gap, http_get, log, measure, record,
                      shares, write_json)

OUT = "rwanda_census.json"
YEAR = 2022
NATIONAL = 13_246_394
SITE = PROCESSED.parent.parent / "site" / "data"
BASE = "https://statistics.gov.rw/sites/default/files/"
MAIN = BASE + "documents/2025-02/PHC5-2022_Main_Indicators.xlsx"
THEMATIC = (BASE + "documents/2025-02/"
            "Population_size_structure_and_spatial%20Distribution_Thematic%20Report.xlsx")
PROFILE = BASE + "2025-05/{name}.pdf"
MAIN_PAGE = ("https://statistics.gov.rw/fifth-population-and-housing-census-2022/"
             "main-indicators-5th-rwanda-population-and-housing-census-phc")
THEMATIC_PAGE = ("https://statistics.gov.rw/data-sources/censuses/Population-and-Housing-Census/"
                 "fifth-population-and-housing-census-2022/rphc5-thematic-reports/"
                 "rphc5-thematic-report-population-size-structure-and-distribution")
SOURCE = ("National Institute of Statistics of Rwanda, Fifth Population and Housing Census "
          "2022, Main Indicators Report, Table 1")
AGE_SOURCE = ("National Institute of Statistics of Rwanda, Fifth Population and Housing Census "
              "2022, Thematic Report: Population Size, Structure and Spatial Distribution, "
              "Tables 4.3 and 4.4")
RELIGION_SOURCE = ("National Institute of Statistics of Rwanda, Fifth Population and Housing "
                   "Census 2022, District Profiles (2023), religious affiliation of the "
                   "resident population")
NATIONALITY_SOURCE = ("National Institute of Statistics of Rwanda, Fifth Population and "
                      "Housing Census 2022, Main Indicators Report, Table 6")
PROFILE_NATIONALITY_SOURCE = ("National Institute of Statistics of Rwanda, Fifth Population "
                              "and Housing Census 2022, District Profiles (2023), Table 2.1, "
                              "resident population by nationality")
LANGUAGE_SOURCE = ("National Institute of Statistics of Rwanda, Fifth Population and Housing "
                   "Census 2022, Main Indicators Report, Table 8")
# Table 8 is "Population aged 15 years and above ... by language" in the sense
# of literacy (its note: "Literacy means here being able to read and write"),
# in combinations ("Kinyarwanda and English"), by province.
LANGUAGE = ("The 2022 census published literacy by language -- the languages people aged 15 "
            "and over can read and write -- and not the languages they speak, so no language "
            "composition is given.")
NATIONALITY_NOTE = ("The 2022 census's count of the resident population by nationality, "
                    "Rwandan or foreign; the census asks no ethnicity.")
LICENCE = "National Institute of Statistics of Rwanda publication (reuse with attribution)"
PROVINCES = {"City of Kigali": ["Nyarugenge", "Gasabo", "Kicukiro"],
             "Southern Province": ["Nyanza", "Gisagara", "Nyaruguru", "Huye", "Nyamagabe",
                                   "Ruhango", "Muhanga", "Kamonyi"],
             "Western Province": ["Karongi", "Rutsiro", "Rubavu", "Nyabihu", "Ngororero",
                                  "Rusizi", "Nyamasheke"],
             "Northern Province": ["Rulindo", "Gakenke", "Musanze", "Burera", "Gicumbi"],
             "Eastern Province": ["Rwamagana", "Nyagatare", "Gatsibo", "Kayonza", "Kirehe",
                                  "Ngoma", "Bugesera"]}
# Table 6 heads the provinces by one word.
SHORT = {"City of Kigali": "City of Kigali", "Southern Province": "Southern",
         "Western Province": "Western", "Northern Province": "Northern",
         "Eastern Province": "Eastern"}
# The profiles' religions, as the map labels them.
RELIGIONS = {"Catholic": "Catholic", "ADEPR": "Pentecostal", "Protestant": "Protestant",
             "Adventist": "Adventist", "Other Christians": "Other Christian",
             "Muslim": "Muslim", "Jehovah witness": "Jehovah's Witnesses",
             "Traditional/Animist": "Traditional", "Other religion": "Other religion",
             "No Religion": "No religion", "Not stated": "Not stated"}
RELIGION_ROW = re.compile(r"^(?P<label>" + "|".join(re.escape(k) for k in RELIGIONS)
                          + r")\s+(?P<count>\d[\d,]*)\b", re.I)


def cells(book: Any, sheet: str) -> list[list[Any]]:
    ws = next((w for w in book.worksheets if w.title.strip() == sheet), None)
    if ws is None:
        raise SystemExit(f"rwanda_census: no sheet {sheet!r}")
    return [list(r) for r in ws.iter_rows(values_only=True)]


def label_of(row: list[Any]) -> str:
    return next((str(c).strip() for c in row if isinstance(c, str) and c.strip()), "")


def numbers(row: list[Any]) -> list[float]:
    return [float(c) for c in row if isinstance(c, (int, float)) and not isinstance(c, bool)]


def read_table1(rows: list[list[Any]]) -> dict[str, dict[str, int]]:
    """{name: {total, male, female}} for Rwanda, the provinces and the districts, checked."""
    out: dict[str, dict[str, int]] = {}
    wanted = {"Rwanda", *PROVINCES, *(d for ds in PROVINCES.values() for d in ds)}
    for row in rows:
        name, figures = label_of(row), numbers(row)
        if name in wanted and len(figures) >= 3:
            total, male, female = (int(f) for f in figures[:3])
            if male + female != total:
                raise SystemExit(f"rwanda_census: {name}: {male:,} men and {female:,} women do "
                                 f"not make {total:,}")
            out[name] = {"total": total, "male": male, "female": female}
    if set(out) != wanted or out["Rwanda"]["total"] != NATIONAL:
        raise SystemExit(f"rwanda_census: Table 1 lacks {sorted(wanted - set(out))}")
    for province, districts in PROVINCES.items():
        made = sum(out[d]["total"] for d in districts)
        if made != out[province]["total"]:
            raise SystemExit(f"rwanda_census: {province}'s districts make {made:,}")
    if sum(out[p]["total"] for p in PROVINCES) != NATIONAL:
        raise SystemExit("rwanda_census: the provinces do not make the country")
    return out


def read_table6(rows: list[list[Any]], table1: dict[str, dict[str, int]]
                ) -> dict[str, dict[str, int]]:
    """{province: {"Rwandan": n, "Foreign nationals": n}}, checked against Table 1."""
    head = next(r for r in rows if any(str(c).strip() == "City of Kigali" for c in r))
    col = {str(c).strip(): i for i, c in enumerate(head) if c is not None}
    lines = {label_of(r).lower(): r for r in rows}
    out = {}
    for province, short in SHORT.items():
        i = col[short]
        total, own, foreign = (int(lines[k][i]) for k in ("total", "rwandan", "foreigners"))
        if own + foreign != total or total != table1[province]["total"]:
            raise SystemExit(f"rwanda_census: Table 6, {province}: {own:,} and {foreign:,} "
                             f"against {total:,} and Table 1's {table1[province]['total']:,}")
        out[province] = {"Rwandan": own, "Foreign nationals": foreign}
    return out


def read_medians(rows43: list[list[Any]], rows44: list[list[Any]]) -> dict[str, float]:
    """{province or district: median age of both sexes}, as Tables 4.3 and 4.4 print it."""
    out: dict[str, float] = {}
    current = None
    for row in rows43:
        name, figures = label_of(row), numbers(row)
        if name in PROVINCES:
            current = name
        elif name.lower() == "total" and current and len(figures) >= 6:
            out[current] = figures[5]
    districts = {d for ds in PROVINCES.values() for d in ds}
    for row in rows44:
        name, figures = label_of(row), numbers(row)
        if name in districts and len(figures) >= 6:
            out[name] = figures[5]
    missing = sorted((set(PROVINCES) | districts) - set(out))
    if missing:
        raise SystemExit(f"rwanda_census: no median age for {missing}")
    return out


def read_religion(text: str, district: str) -> dict[str, int] | None:
    """The profile's religions for the district, in counts; None if the table is not found."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    head = re.compile(rf"^{re.escape(district)}\s+district\s+(\d[\d,]*)\b", re.I)
    for i, line in enumerate(lines):
        hit = head.match(line)
        if not hit or not any(RELIGION_ROW.match(x) and x.lower().startswith("catholic")
                              for x in lines[i + 1:i + 3]):
            continue
        counts: dict[str, int] = {}
        for row in lines[i + 1:i + 20]:
            if row.lower().startswith("source"):
                break
            got = RELIGION_ROW.match(row)
            if got:
                label = next(k for k in RELIGIONS if k.lower() == got["label"].lower())
                counts[RELIGIONS[label]] = int(got["count"].replace(",", ""))
        counts["_total"] = int(hit.group(1).replace(",", ""))
        return counts
    return None


NATIONALITY_TABLE = re.compile(r"nationality\s+and\s+sector", re.I)


def read_nationality(text: str, district: str) -> dict[str, int] | None:
    """The district's own row of its profile's Table 2.1 -- everyone, Rwandans,
    foreigners, then 100 and the two shares -- as {"Rwandan": n, "Foreign
    nationals": n, "_total": n}; None if no such row follows the table's title
    or its figures do not agree with each other.

    The title also appears in the list of tables, with no rows after it; the
    religion table's own district row has three counts too (everyone, urban,
    rural) but then 100 three times, not the two shares.
    """
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    number = r"(\d[\d,]*)"
    share = r"(\d{1,2}(?:\.\d+)?)"
    row = re.compile(rf"^{re.escape(district)}\s+district\s+{number}\s+{number}\s+{number}"
                     rf"\s+100(?:\.0+)?\s+{share}\s+{share}\s*$", re.I)
    for i, line in enumerate(lines):
        if not NATIONALITY_TABLE.search(line):
            continue
        for candidate in lines[i + 1:i + 12]:
            hit = row.match(candidate)
            if not hit:
                continue
            total, own, foreign = (int(hit.group(k).replace(",", "")) for k in (1, 2, 3))
            if own + foreign != total or total <= 0 \
                    or abs(100 * own / total - float(hit.group(4))) > 0.01 \
                    or abs(100 * foreign / total - float(hit.group(5))) > 0.01:
                return None
            return {"Rwandan": own, "Foreign nationals": foreign, "_total": total}
    return None


def profile_text(name: str) -> tuple[str, str] | None:
    """A district profile's text and URL; the files are named in more than one case."""
    from pypdf import PdfReader                    # noqa: PLC0415
    for variant in (name, name.upper(), name.lower()):
        url = PROFILE.format(name=variant)
        try:
            blob = http_get(url, binary=True, cache=False, timeout=180, retries=1)
        except Exception as err:                    # noqa: BLE001 -- a miss is logged
            log(f"  {url}: {type(err).__name__}")
            continue
        if not blob.startswith(b"%PDF"):
            continue
        log(f"  read {url}: {len(blob):,} bytes, sha256 {hashlib.sha256(blob).hexdigest()}")
        reader = PdfReader(io.BytesIO(blob))
        return "\n".join((p.extract_text() or "") for p in reader.pages), url
    return None


def religions(table1: dict[str, dict[str, int]]
              ) -> tuple[dict[str, dict[str, int]], dict[str, dict[str, int]], dict[str, str]]:
    """{district: religion counts} and {district: nationality counts} for the
    profiles whose tables read whole, and {district: url}."""
    out, nations, urls = {}, {}, {}
    for districts in PROVINCES.values():
        for d in districts:
            got = profile_text(d)
            if got is None:
                log(f"  {d}: no profile found")
                continue
            text, url = got
            urls[d] = url
            nationality = read_nationality(text, d)
            if nationality is None or nationality.pop("_total") != table1[d]["total"]:
                log(f"  {d}: no nationality row agreeing with Table 1 in its profile")
            else:
                nations[d] = nationality
            counts = read_religion(text, d)
            if counts is None:
                log(f"  {d}: no religion table in its profile")
                continue
            total = counts.pop("_total")
            made = sum(counts.values())
            if total != table1[d]["total"] or made != total or len(counts) != len(RELIGIONS):
                log(f"  {d}: religions make {made:,} of {total:,} (Table 1: "
                    f"{table1[d]['total']:,}), {len(counts)} rows; not written")
                continue
            out[d] = counts
    return out, nations, urls


def fields(name: str, table1: dict[str, dict[str, int]], medians: dict[str, float],
           religion: dict[str, int] | None, url: str | None, of: str) -> dict[str, Any]:
    row = table1[name]
    out: dict[str, Any] = {
        "population": measure(row["total"], year=YEAR, source=SOURCE),
        "population_note": f"The 2022 census's count of everyone resident in the {of}.",
        "sex_ratio": measure(round(1000 * row["male"] / row["female"]),
                             unit="males_per_1000_females", year=YEAR, source=SOURCE),
        "median_age": measure(medians[name], unit="years", year=YEAR, source=AGE_SOURCE),
        "median_age_note": ("The 2022 census's median age of the resident population, as the "
                            "Institute prints it, in whole years."),
        "language": gap(NOT_AVAILABLE, LANGUAGE),
        "sources": [{"field": "population/sex_ratio", "name": SOURCE, "url": MAIN_PAGE,
                     "year": YEAR, "license": LICENCE},
                    {"field": "median_age", "name": AGE_SOURCE, "url": THEMATIC_PAGE,
                     "year": YEAR, "license": LICENCE},
                    {"field": "language", "name": LANGUAGE_SOURCE, "url": MAIN_PAGE,
                     "year": YEAR, "license": LICENCE}]}
    if religion:
        rows = shares(religion, total=row["total"])
        out.update(religion=rows, religion_year=dated(rows, YEAR),
                   religion_note=("The 2022 census's count of the resident population by "
                                  "religious affiliation"
                                  + (", the province's districts added up" if of == "province"
                                     else "")
                                  + ". 'Pentecostal' is the census's ADEPR, the Association of "
                                    "Pentecostal Churches of Rwanda; 'Protestant' and "
                                    "'Adventist' are its own separate categories."))
        out["sources"].append({"field": "religion", "name": RELIGION_SOURCE,
                               "url": url or MAIN_PAGE, "year": YEAR, "license": LICENCE})
    return out


def build(table1: dict[str, dict[str, int]], table6: dict[str, dict[str, int]],
          medians: dict[str, float], faiths: dict[str, dict[str, int]], urls: dict[str, str],
          admin1: list[dict[str, Any]], admin2: list[dict[str, Any]],
          nations: dict[str, dict[str, int]] | None = None) -> list[dict[str, Any]]:
    records = []
    nations = dict(nations or {})
    shapes1 = {s["name"].strip(): s for s in admin1}
    shapes2 = {s["name"].strip(): s for s in admin2}
    for province, districts in PROVINCES.items():
        shape = shapes1.get(province)
        if shape is None:
            raise SystemExit(f"rwanda_census: no polygon for {province}")
        summed = None
        if all(d in faiths for d in districts):
            summed = {g: sum(faiths[d][g] for d in districts) for g in faiths[districts[0]]}
        # The profiles' nationality rows stand only where the province's districts
        # make Table 6's Rwandans and foreigners between them; a profile misread
        # is a whole province's worth of doubt.
        if all(d in nations for d in districts):
            made = {g: sum(nations[d][g] for d in districts) for g in table6[province]}
            if made != table6[province]:
                log(f"  {province}: its districts' profiles make {made}, not Table 6's "
                    f"{table6[province]}; no district nationality written")
                for d in districts:
                    nations.pop(d, None)
        extra = fields(province, table1, medians, summed, None, "province")
        nationality = shares(table6[province], total=table1[province]["total"])
        extra.update(ethnicity=nationality, ethnicity_basis="nationality",
                     ethnicity_year=dated(nationality, YEAR), ethnicity_note=NATIONALITY_NOTE)
        extra["sources"].append({"field": "ethnicity", "name": NATIONALITY_SOURCE,
                                 "url": MAIN_PAGE, "year": YEAR, "license": LICENCE})
        records.append(record(f"RWA-2022-{shape['id']}", province, level="admin1", parent="RWA",
                              country="RWA", match_by="shape_id", shape_id=shape["id"], **extra))
        for d in districts:
            shape2 = shapes2.get(d)
            if shape2 is None:
                raise SystemExit(f"rwanda_census: no polygon for {d}")
            extra = fields(d, table1, medians, faiths.get(d), urls.get(d), "district")
            if d in nations:
                rows = shares(nations[d], total=table1[d]["total"])
                extra.update(ethnicity=rows, ethnicity_basis="nationality",
                             ethnicity_year=dated(rows, YEAR), ethnicity_note=NATIONALITY_NOTE)
                extra["sources"].append({"field": "ethnicity", "name": PROFILE_NATIONALITY_SOURCE,
                                         "url": urls.get(d) or MAIN_PAGE, "year": YEAR,
                                         "license": LICENCE})
            else:
                extra["ethnicity"] = gap(NOT_AVAILABLE, "Rwanda's 2022 census asks no ethnicity.")
            records.append(record(f"RWA-2022-{shape2['id']}", d, level="admin2", parent="RWA",
                                  country="RWA", match_by="shape_id", shape_id=shape2["id"],
                                  **extra))
    return records


def workbook(url: str) -> Any:
    import openpyxl                                 # noqa: PLC0415
    blob = http_get(url, binary=True, cache=False, timeout=300)
    log(f"  read {url}: {len(blob):,} bytes, sha256 {hashlib.sha256(blob).hexdigest()}")
    return openpyxl.load_workbook(io.BytesIO(blob), read_only=True, data_only=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", default="", help="a label that tells two dispatches apart; ignored")
    ap.parse_args()
    main_book, thematic = workbook(MAIN), workbook(THEMATIC)
    table1 = read_table1(cells(main_book, "Table 1"))
    table6 = read_table6(cells(main_book, "Table 6"), table1)
    medians = read_medians(cells(thematic, "Table 4.3"), cells(thematic, "Table 4.4"))
    log(f"  Table 1: 5 provinces and 30 districts making {NATIONAL:,}; Table 6: nationality "
        f"by province; Tables 4.3 and 4.4: {len(medians)} medians")
    faiths, nations, urls = religions(table1)
    log(f"  religion read whole for {len(faiths)} of 30 districts, nationality for "
        f"{len(nations)}")
    admin1 = json.loads((SITE / "admin1" / "RWA.units.json").read_text())
    admin2 = json.loads((SITE / "admin2" / "RWA.units.json").read_text())
    records = build(table1, table6, medians, faiths, urls, admin1, admin2, nations)
    for r in records:
        lead = r["religion"][0]["group"] if isinstance(r.get("religion"), list) else "-"
        foreign = next((g["count"] for g in r["ethnicity"] if g["group"] == "Foreign nationals"),
                       None) if isinstance(r.get("ethnicity"), list) else None
        log(f"  {r['level']} {r['name']}: {r['population']['value']:,}, median "
            f"{r['median_age']['value']}, sex ratio {r['sex_ratio']['value']}, religion led by "
            f"{lead}, foreign nationals {foreign if foreign is not None else '-'}")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
