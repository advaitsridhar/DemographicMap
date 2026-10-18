#!/usr/bin/env python3
"""Somalia: the 2014 Population Estimation Survey's median age and sex ratio by region.

Somalia has published no census since 1975 (the 1986-87 count was never
released). The Population Estimation Survey of 2014 (PESS), run by the Somali
authorities with UNFPA, sampled households in the urban, rural, camp and nomadic
strata of each of the 18 regions of 1986, the regions the map draws, and its
second analytical volume -- *Population Composition and Demographic
Characteristics of the Somali People* (UNFPA, 2016), held on the National
Bureau of Statistics' site -- prints two tables by region:

* Table 2, *Population by region and sex*: each region's men and women as
  shares of its people, to a tenth of a percent. Men per 1,000 women follow
  from them, good to about three either way.
* Table A.2, *Median age by type of residence and region*: the median age of
  each region's men, women and everyone, in whole years.

Both are survey estimates, so they go in a *_survey.json, which fills and
replaces no count. Middle Juba is written with neither: the report says the
region was inaccessible because of the militia, and its Table A.2 gives its men
a median of 30 years against its women's 18.

The districts the map draws are the 118 of today, and the survey's tables are
by region: its report estimates the population of the 18 regions only (the
district figures that circulate were derived afterwards from UNDP's 2005
district estimates, for the 74 districts of 1986). The 2020 Somali Health and
Demographic Survey likewise reports ages and sexes for regions at most.
``somalia_districts.json`` gives each district a stated reason for its
population, median age and sex ratio.

Usage:
    python -m scripts.fetch_census.somalia_survey
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, gap, http_get, log, measure, record, write_json
from .binding import fold

OUT = "somalia_survey.json"
DISTRICTS = "somalia_districts.json"
YEAR = 2014
SITE = PROCESSED.parent.parent / "site" / "data"
URL = ("https://nbs.gov.so/wp-content/uploads/2023/07/Population-Composition-and-Demographic-"
       "Characteristics-of-the-Somali-People-%E2%80%93-Volume-2.pdf")
SOURCE = ("UNFPA Somalia with the Somali authorities, Population Estimation Survey 2014, "
          "Volume 2: Population Composition and Demographic Characteristics of the Somali People "
          "(2016)")
LICENCE = "UNFPA publication; reproduction permitted with the source acknowledged"
BASIS = ("survey estimate: a sample of households in each region's urban, rural, camp and "
         "nomadic strata")
# The tables' names for regions where they are not the map's, folded.
ALIASES = {"wgalbeed": "woqooyigalbeed", "mshabelle": "middleshebelle",
           "middleshabelle": "middleshebelle", "lshabelle": "lowershebelle",
           "lowershabelle": "lowershebelle", "mjuba": "middlejuba", "ljuba": "lowerjuba",
           "hiraan": "hiiraan"}
# The 2020 survey, which like the 2014 one publishes ages and sexes for regions
# at most: its main report and one report per region.
SHDS = ("Federal Government of Somalia, Directorate of National Statistics, with UNFPA, The "
        "Somali Health and Demographic Survey 2020 (main report and regional reports)")
SHDS_URL = "https://somalia.unfpa.org/en/publications/somali-health-and-demographic-survey-2020"
SHDS_YEAR = 2020
SHDS_LICENCE = "UNFPA publication; reproduction permitted with the source acknowledged"
# What every district says for its population, median age and sex ratio. The
# survey's report estimates the population of the 18 regions only; the
# district figures that circulate (HDX's "Somalia Population Data - UNFPA
# 2014") were derived afterwards from UNDP's 2005 district estimates, and are
# for the 74 districts of 1986, not the 118 the map draws.
DISTRICT_POPULATION = (
    "Somalia has published no census since 1975. The 2014 Population Estimation Survey "
    "published estimates for the 18 regions only; none is published for a district drawn "
    "today.")
DISTRICT_AGES = (
    "Somalia has published no census since 1975. The 2014 Population Estimation Survey and "
    "the 2020 Somali Health and Demographic Survey published ages and sexes for regions at "
    "most; neither gives them for a district.")
# Regions the survey could not reach, with what its report says.
UNREACHED = {"middlejuba": ("The 2014 Population Estimation Survey's report says Middle Juba "
                            "was inaccessible because of the militia, and its median age for "
                            "the region's men, 30 years against its women's 18, is no "
                            "estimate of the region's people; nothing is given for it.")}
SHARE = re.compile(r"^(?P<name>[A-Z][A-Za-z. ]+?)\s+(?P<male>\d{2}\.\d)\s+(?P<female>\d{2}\.\d)"
                   r"\s+(?P<share>\d{1,3}(?:\.\d)?)$")
MEDIAN = re.compile(r"^(?P<name>[A-Z][A-Za-z ]+?)\s+(?P<male>\d{1,2})\s+(?P<female>\d{1,2})"
                    r"\s+(?P<total>\d{1,2})$")


def key(name: str) -> str:
    k = fold(name)
    return ALIASES.get(k, k)


def read_shares(text: str) -> dict[str, dict[str, float]]:
    """Table 2's rows: {region key: {name, male, female, share}}, checked."""
    start = text.find("Percent distribution by sex")
    end = text.find("Table 2:", start)
    if start < 0 or end < 0:
        raise SystemExit("somalia_survey: Table 2 (population by region and sex) not found")
    out: dict[str, dict[str, float]] = {}
    total = None
    for line in text[start:end].splitlines():
        hit = SHARE.match(line.strip())
        if not hit:
            continue
        row = {"name": hit["name"].strip(), "male": float(hit["male"]),
               "female": float(hit["female"]), "share": float(hit["share"])}
        if abs(row["male"] + row["female"] - 100) > 0.11:
            raise SystemExit(f"somalia_survey: {row['name']}: {row['male']} and {row['female']} "
                             "do not make 100")
        if row["name"].lower().startswith("all regions"):
            total = row
            continue
        out[key(row["name"])] = row
    shares = sum(r["share"] for r in out.values())
    if len(out) != 18 or total is None or abs(shares - 100) > 0.5:
        raise SystemExit(f"somalia_survey: Table 2 gives {len(out)} regions making "
                         f"{shares:.1f}% (total row {bool(total)})")
    return out


def read_medians(text: str) -> dict[str, dict[str, int]]:
    """Table A.2's region rows: {region key: {name, male, female, total}}, checked."""
    # The last mention: the list of tables at the front names it too.
    start = text.rfind("Table A. 2")
    if start < 0:
        raise SystemExit("somalia_survey: Table A.2 (median age by region) not found")
    body = text[start:]
    body = body[body.find("Region"):]
    out: dict[str, dict[str, int]] = {}
    for line in body.splitlines():
        hit = MEDIAN.match(line.strip())
        if not hit:
            continue
        name = hit["name"].strip()
        if name.lower() == "total":
            break
        out[key(name)] = {"name": name, "male": int(hit["male"]), "female": int(hit["female"]),
                          "total": int(hit["total"])}
    if len(out) != 18:
        raise SystemExit(f"somalia_survey: Table A.2 gives {len(out)} regions: {sorted(out)}")
    return out


def build(shares: dict[str, dict[str, float]], medians: dict[str, dict[str, int]],
          admin1: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key = {key(s["name"]): s for s in admin1}
    if set(by_key) != set(shares) or set(shares) != set(medians):
        raise SystemExit(f"somalia_survey: regions differ: map {sorted(set(by_key) - set(shares))}"
                         f", Table 2 {sorted(set(shares) - set(by_key))}, Table A.2 "
                         f"{sorted(set(medians) - set(by_key))}")
    records = []
    for k, shape in sorted(by_key.items()):
        cite = [{"field": "median_age/sex_ratio", "name": SOURCE, "url": URL, "year": YEAR,
                 "license": LICENCE}]
        if k in UNREACHED:
            stated = gap(NOT_AVAILABLE, UNREACHED[k])
            fields: dict[str, Any] = {"median_age": stated, "sex_ratio": stated}
            cite[0]["field"] = "median_age note/sex_ratio note"
        else:
            s, m = shares[k], medians[k]
            fields = {
                "median_age": measure(m["total"], unit="years", year=YEAR, source=SOURCE),
                "median_age_basis": BASIS,
                "median_age_note": (
                    f"The 2014 Population Estimation Survey's median age for the region's "
                    f"people, in whole years (men {m['male']}, women {m['female']}): a survey "
                    "estimate, not a count. Somalia has published no census since 1975."),
                "sex_ratio": measure(round(1000 * s["male"] / s["female"]),
                                     unit="males_per_1000_females", year=YEAR, source=SOURCE),
                "sex_ratio_basis": BASIS,
                "sex_ratio_note": (
                    f"From the 2014 Population Estimation Survey's shares of men and women in "
                    f"the region's people, {s['male']:.1f}% and {s['female']:.1f}%, printed to a "
                    "tenth of a percent, so good to about three either way: a survey estimate, "
                    "not a count."),
            }
        records.append(record(f"SOM-PESS-{shape['id']}", shape["name"].strip(), level="admin1",
                              parent="SOM", country="SOM", match_by="shape_id",
                              shape_id=shape["id"], sources=cite, **fields))
    return records


def districts(admin2: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """A stated reason for every district's population, median age and sex ratio."""
    population = gap(NOT_AVAILABLE, DISTRICT_POPULATION)
    ages = gap(NOT_AVAILABLE, DISTRICT_AGES)
    cite = [{"field": "population note/median_age note/sex_ratio note", "name": SOURCE,
             "url": URL, "year": YEAR, "license": LICENCE},
            {"field": "median_age note/sex_ratio note", "name": SHDS, "url": SHDS_URL,
             "year": SHDS_YEAR, "license": SHDS_LICENCE}]
    return [record(f"SOM-PESS-{s['id']}", s["name"].strip(), level="admin2", parent="SOM",
                   country="SOM", match_by="shape_id", shape_id=s["id"], population=population,
                   median_age=ages, sex_ratio=ages, sources=cite) for s in admin2]


def read_text(blob: bytes) -> str:
    from pypdf import PdfReader                    # noqa: PLC0415
    reader = PdfReader(io.BytesIO(blob))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", default="", help="a label that tells two dispatches apart; ignored")
    ap.parse_args()
    blob = http_get(URL, binary=True, cache=False, timeout=300)
    if not blob.startswith(b"%PDF"):
        raise SystemExit(f"somalia_survey: {URL} is not a PDF: {blob[:80]!r}")
    log(f"  read {URL}: {len(blob):,} bytes, sha256 {hashlib.sha256(blob).hexdigest()}")
    text = read_text(blob)
    shares, medians = read_shares(text), read_medians(text)
    log(f"  Table 2: 18 regions by sex; Table A.2: 18 regions' medians")
    admin1 = json.loads((SITE / "admin1" / "SOM.units.json").read_text())
    admin2 = json.loads((SITE / "admin2" / "SOM.units.json").read_text())
    records = build(shares, medians, admin1)
    for r in records:
        m, s = r["median_age"], r["sex_ratio"]
        log(f"  {r['name']}: median {m.get('value', 'stated')}, sex ratio "
            f"{s.get('value', 'stated')}")
    write_json(PROCESSED / OUT, records)
    write_json(PROCESSED / DISTRICTS, districts(admin2))
    log(f"  {len(admin2)} districts given stated reasons")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
