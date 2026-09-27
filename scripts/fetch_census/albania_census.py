#!/usr/bin/env python3
"""Albania: ethnicity, religion and home language by prefecture, 2023 census.

The Institute of Statistics (INSTAT) published the 2023 Population and
Housing Census's cultural tables by prefecture (qark), one workbook per
question with a sheet per prefecture, each by sex:

* Tab. 1.12 -- resident population by ethnicity (përkatësia etnike);
* Tab. 1.13 -- by religion (besimi fetar);
* Tab. 1.14 -- by the language usually spoken at home (not mother tongue,
  which the 2011 census asked instead).

The three questions were voluntary. "Not available" (nuk disponohet) is the
census's own row for residents whose record came from administrative sources
rather than an interview -- 134,451 people, 5.6% of the country -- and is kept
as a bar of its own, as are "prefer not to answer" and "none". A cell INSTAT
prints as ".." (a count too small to publish) is left out of its row and the
people it hides are kept together as one bar, so every row still adds to its
prefecture.

The prefectures keep Eurostat's newer head count, median age and sex ratio;
this writes their compositions. INSTAT publishes nothing of the three by the
36 former districts the map draws at the second level -- the 2023 census is
by prefecture and by the 61 municipalities of 2015, the 2011 census by
prefecture and by the 373 municipalities and communes of its day, and no
table carries the district a commune belonged to -- so the districts are left
as they are.

Checks: every row's categories (with what the ".." cells hide) add to its
total, the sexes to the total, the three tables agree on each prefecture's
count and with Tab. 6's, and the prefectures add to the country.

Usage:
    python -m scripts.fetch_census.albania_census
"""

from __future__ import annotations

import argparse
import re
import urllib.parse
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, gap, http_get, log, record, shares, write_json
from .balkans_common import check_sum, fold, shapes, spreadsheetml

OUT = "albania_census.json"
YEAR = 2023
MEDIA = "https://www.instat.gov.al/media/"
TABLES = {
    "ethnicity": MEDIA + "14409/tab_1_12_popullsia-banuese-sipas-përkatësisë-etnike-dhe-gjinisë_qarqe.xls",
    "religion": MEDIA + "14411/tab_1_13_popullsia-banuese-sipas-besimit-fetar-dhe-gjinisë_qarqe.xls",
    "language": MEDIA + "14412/tab_1_14_popullsia-banuese-sipas-gjuhës-që-flitet-zakonisht-në-shtëpi-dhe-gjinisë_qarqe.xls",
}
TITLES = {
    "ethnicity": "Tab. 1.12, resident population by ethnicity and sex, by prefecture",
    "religion": "Tab. 1.13, resident population by religion and sex, by prefecture",
    "language": ("Tab. 1.14, resident population by language usually spoken at home and sex, "
                 "by prefecture"),
}
PAGE = "https://www.instat.gov.al/en/themes/censuses/census-of-population-and-housing/"
SOURCE = "Institute of Statistics of Albania (INSTAT), Population and Housing Census 2023, {title}"
LICENCE = "Institute of Statistics of Albania (reuse with attribution)"
NATIONAL = 2_402_113
SUPPRESSED = "Suppressed (disclosure control)"
# The Albanian half of a row's label, folded, as it begins -> the bar. The
# longer beginnings are tried first ("myslimanbektashi" before "mysliman").
LABELS: dict[str, dict[str, str]] = {
    "ethnicity": {
        "shqiptare": "Albanian", "greke": "Greek", "maqedonase": "Macedonian",
        "malazeze": "Montenegrin", "aromune": "Aromanian", "rome": "Roma",
        "egjyptiane": "Balkan Egyptian", "boshnjake": "Bosniak", "serbe": "Serbian",
        "bullgare": "Bulgarian", "tjetergrupetnokulturor": "Other",
        "grupetnokulturoriperzier": "Mixed", "asnje": "None",
        "preferojtemospergjigjem": "Not declared", "nukdisponohet": "Not stated",
    },
    "religion": {
        "myslimanbektashi": "Bektashi", "mysliman": "Islam",
        "krishterekatolik": "Catholic", "krishtereortodoks": "Orthodox",
        "krishtereungjillore": "Protestant", "tjeterbesimfetar": "Other religion",
        "besimtaretepacilesuar": "Unaffiliated believer",
        "besimtaretepacilcesuar": "Unaffiliated believer", "ateist": "Atheism",
        "asnje": "No religion", "preferojtemospergjigjem": "Not declared",
        "nukdisponohet": "Not stated",
    },
    "language": {
        "shqip": "Albanian", "gjuhetjeter": "Other", "disagjuhe": "Mixed languages",
        "preferojtemospergjigjem": "Not declared", "nukdisponohet": "Not stated",
    },
}
WHY_DISTRICT = ("INSTAT publishes the 2023 census by prefecture and by the 61 municipalities of "
                "2015, and the 2011 census by prefecture and by the 373 municipalities and "
                "communes of its day; none of its tables is by the 36 former districts the map "
                "draws here, or carries the district a commune belonged to, so no figure of this "
                "field exists for the district.")
NOTES = {
    "ethnicity": ("Ethnic affiliation (përkatësia etnike), 2023 census, resident population, a "
                  "voluntary question. 'Not stated' is the census's 'not available': residents "
                  "whose record came from administrative sources rather than an interview. "
                  "Those who preferred not to answer, who named none, or who named a mixed "
                  "affiliation are their own bars; 'Balkan Egyptian' is the census's Egjyptiane."),
    "religion": ("Religion (besimi fetar), 2023 census, resident population, a voluntary "
                 "question. 'Unaffiliated believer' is the census's believers without a "
                 "denomination (besimtarë të pacilësuar); Bektashi are counted apart from other "
                 "Muslims, as the census does. 'Not stated' is the census's 'not available': "
                 "residents whose record came from administrative sources."),
    "language": ("Language usually spoken at home, 2023 census, resident population -- not "
                 "mother tongue, which the 2011 census asked instead. INSTAT publishes Albanian, "
                 "any other language, and several languages; 'Not stated' is the census's 'not "
                 "available': residents whose record came from administrative sources."),
}


def label_of(field: str, text: str) -> str | None:
    """The bar a row is shown as; None for the total row; '' if unknown."""
    f = fold(text)
    if f.startswith("gjithsej"):
        return None
    for start in sorted(LABELS[field], key=len, reverse=True):
        if f.startswith(start):
            return LABELS[field][start]
    return ""


def cell(value: Any) -> float | None:
    """A count; None for INSTAT's '..' (too small to publish)."""
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value or "").strip()
    if text in ("..", "…"):
        return None
    if text in ("", "-"):
        return 0.0
    return float(text.replace(",", ""))


def read(field: str) -> dict[str, dict[str, Any]]:
    """{prefecture (folded): {"name", "total", "men", "women", "groups"}}."""
    # The file names carry ë: sent percent-encoded, as a browser sends them.
    blob = http_get(urllib.parse.quote(TABLES[field], safe=":/%?=&"), binary=True, timeout=300)
    sheets = spreadsheetml(blob)
    out: dict[str, dict[str, Any]] = {}
    unknown = set()
    for sheet, rows in sheets.items():
        # "Qarku Berat | Prefecture Berat": the prefecture as the table names it.
        head = next((str(r[0]) for r in rows if r and str(r[0] or "").strip().lower().startswith("qarku")), None)
        if head is None:
            raise SystemExit(f"albania_census: {field}: sheet {sheet!r} names no prefecture")
        # One cell or two: "Qarku Fier" | "Prefecture Fier", or "Qarku Fier  Prefecture Fier".
        name = re.match(r"Qarku\s+(.+?)(?:\s{2,}|\s+Prefecture\b|$)", head.strip()).group(1).strip()
        unit: dict[str, Any] = {"name": name, "groups": {}, "hidden": 0}
        for r in rows:
            if not r or r[0] is None or len(r) < 4:
                continue
            label = label_of(field, str(r[0]))
            if label == "":
                if cell_is_number(r[1]) or str(r[1] or "").strip() == "..":
                    unknown.add(str(r[0]).strip())
                continue
            total, men, women = (cell(v) for v in r[1:4])
            if label is None:
                unit["total"], unit["men"], unit["women"] = total, men, women
                continue
            if total is None:
                unit["hidden"] += 1
                continue
            unit["groups"][label] = unit["groups"].get(label, 0.0) + total
        if "total" not in unit:
            raise SystemExit(f"albania_census: {field}: no total row for {name}")
        check_sum(unit["men"] + unit["women"], unit["total"], f"albania_census: {field} sexes of {name}")
        shown = sum(unit["groups"].values())
        short = unit["total"] - shown
        if unit["hidden"]:
            if short < 0:
                raise SystemExit(f"albania_census: {field} of {name}: rows add to {shown:,.0f}, "
                                 f"more than the total {unit['total']:,.0f}")
            if short:
                unit["groups"][SUPPRESSED] = short
        else:
            check_sum(shown, unit["total"], f"albania_census: {field} of {name}")
        out[fold(name)] = unit
    if unknown:
        raise SystemExit(f"albania_census: {field} rows with no label: {sorted(unknown)}")
    check_sum(sum(u["total"] for u in out.values()), NATIONAL, f"albania_census: {field}, prefectures")
    log(f"  {field}: {len(out)} prefectures; hidden cells in "
        f"{sum(1 for u in out.values() if u['hidden'])}")
    return out


def cell_is_number(value: Any) -> bool:
    if value is None or not str(value).strip():
        return False
    try:
        return cell(value) is not None
    except ValueError:
        return False


def build() -> list[dict[str, Any]]:
    tables = {f: read(f) for f in ("ethnicity", "religion", "language")}
    polys = {fold(s["name"]): s for s in shapes("ALB", "admin1")}
    names = set(tables["ethnicity"])
    for f, t in tables.items():
        if set(t) != names:
            raise SystemExit(f"albania_census: the {f} table's prefectures differ: {sorted(set(t) ^ names)}")
    records = []
    bound = set()
    for key in sorted(names):
        shape = polys.get(key) or next((s for k, s in polys.items() if k[:5] == key[:5]), None)
        if shape is None or shape["id"] in bound:
            raise SystemExit(f"albania_census: no single polygon for the prefecture {key!r}; "
                             f"polygons {sorted(polys)}")
        bound.add(shape["id"])
        total = tables["ethnicity"][key]["total"]
        fields: dict[str, Any] = {}
        cites = []
        for f in ("ethnicity", "religion", "language"):
            unit = tables[f][key]
            check_sum(unit["total"], total, f"albania_census: {f} against ethnicity for {unit['name']}")
            fields[f] = shares({k: v for k, v in unit["groups"].items() if v}, total=unit["total"])
            fields[f"{f}_year"] = YEAR
            fields[f"{f}_note"] = NOTES[f] + (
                f" {unit['groups'].get(SUPPRESSED, 0):,.0f} people in cells INSTAT does not publish "
                "(too few to show) are one bar." if SUPPRESSED in unit["groups"] else "")
            cites.append({"field": f, "name": SOURCE.format(title=TITLES[f]), "url": TABLES[f],
                          "page": PAGE, "year": YEAR, "license": LICENCE})
        records.append(record(f"ALB-2023-{key}", shape["name"], level="admin1", parent="ALB",
                              country="ALB", match_by="shape_id", shape_id=shape["id"],
                              sources=cites, **fields))
        eth = fields["ethnicity"][:3]
        log(f"  {shape['name']}: {total:,.0f}; " + ", ".join(f"{r['group']} {r['pct']}" for r in eth))
    spare = [s["name"] for s in polys.values() if s["id"] not in bound]
    if spare:
        raise SystemExit(f"albania_census: prefectures with no table: {spare}")
    # The 36 former districts: no table of any of these fields reaches them.
    for s in shapes("ALB", "admin2"):
        records.append(record(
            f"ALB-district-{s['id']}", s["name"], level="admin2", parent="ALB", country="ALB",
            match_by="shape_id", shape_id=s["id"],
            **{f: gap(NOT_AVAILABLE, WHY_DISTRICT) for f in
               ("median_age", "sex_ratio", "religion", "language", "ethnicity")}))
    return records


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.parse_args()
    log("albania_census: INSTAT, 2023 census by prefecture")
    records = build()
    write_json(PROCESSED / OUT, records)
    log(f"  wrote {OUT}: {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
