#!/usr/bin/env python3
"""The Emirate of Abu Dhabi: population and sex in SCAD's register-based census.

The Statistics Centre - Abu Dhabi (SCAD) publishes the Abu Dhabi Census on
census.scad.gov.ae: the census of 2023, revised ("2023 R1"), and the 2024
figures, both drawn from the emirate's integrated administrative registers.
The site's front page draws the population by sex as charts whose data it
carries inline -- the emirate's men and women for 2024 and for 2023 R1, then
each of its three regions' (Abu Dhabi, Al Ain, Al Dhafra) for the same two
years -- and states the totals in its text ("Abu Dhabi's population reached
4.14 million in 2024 ... Al Ain 23.9% (986,910), and Al Dhafra 7.9%
(325,735)").

**What is written.** The drawn "Abu Dhabi" emirate: its 2024 population and
males per hundred females. The boundary file draws the seven emirates at
both levels under one id, so the record is written at both
(``second_level_twins``).

**What is not, and why.** The census site publishes the emirate's people by
sex and region only: no age groups (so no median age), no nationality, and
no religion or language. Each field says so.

**The other six emirates** are not SCAD's. Each drawn one gets a record that
says why it has no median age or sex ratio (``OTHERS``): Dubai's statistics
centre publishes its population by sex and age group, but its site
(dsc.gov.ae) answered "The requested URL was rejected", and no such table was
found among the Internet Archive's copies of its reports; Sharjah's
statistics department (dscd.sharjah.ae) could not be reached; for the four
northern emirates, the federal centre's site (fcsc.gov.ae) answered 403 and
the open-data portal (bayanat.ae) returned no dataset for population. A
drawn emirate without a reason stops the run.

**Checks** (any failure stops the run and nothing is written): the page
carries the emirate and its three regions for exactly two years; in each
year the regions make the emirate, men and women alike; the larger year is
the one whose total the page's sentence gives ("4.14 million in 2024"),
and its Al Ain and Al Dhafra totals are the ones the sentence prints; the
smaller is the 2023 R1 total the page gives ("3.85 million"); exactly one
drawn emirate is Abu Dhabi.

Usage:
    python -m scripts.fetch_census.uae_scad
"""

from __future__ import annotations

import argparse
import html
import re
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, gap, http_get, log, measure, record, write_json
from .west_asia_common import check, second_level_twins, sex_ratio, units

ISO3 = "ARE"
OUT = "uae_scad.json"
URL = "https://census.scad.gov.ae/"
YEAR = 2024
EARLIER = "2023 R1"
SOURCE = ("Statistics Centre - Abu Dhabi (SCAD), Abu Dhabi Census: population by region "
          "and sex, 2024 (integrated administrative registers)")
LICENCE = "Statistics Centre - Abu Dhabi, published census results"
DRAWN = "Abu Dhabi"
REGIONS = ("AbuDhabi", "AlAin", "AlDhafra")
# A chart's data: {"city": "AlAin", "male": 622295, "female": 364615, }
CHART = re.compile(r'chart\.data\s*=\s*\[\{\s*"city"\s*:\s*"([^"]+)"\s*,\s*"male"\s*:\s*"?'
                   r'(\d+)"?\s*,\s*"female"\s*:\s*"?(\d+)"?\s*,?\s*\}\]')
# "Abu Dhabi's population reached 4.14 million in 2024"
LATEST = re.compile(r"population reached ([\d.]+) million in (\d{4})")
EARLIER_TOTAL = re.compile(r"population reached ([\d.]+) million in the 2023 R1 update")
SHARE = re.compile(r"(Al Ain|Al Dhafra) [\d.]+% \(([\d,]+)\)")
PUBLISHED = ("SCAD's census site (census.scad.gov.ae) publishes the emirate's population by "
             "sex and region only")
AGE_WHY = f"{PUBLISHED}: no age groups, so no median age can be taken."
NATIONALITY_WHY = (f"{PUBLISHED}: no nationality (citizens or not), so no nationality split is "
                   "published for the emirate.")
RELIGION_WHY = f"{PUBLISHED}: no religion."
LANGUAGE_WHY = f"{PUBLISHED}: no language."
# Why each of the other emirates carries no median age or sex ratio.
FEDERAL = ("the federal statistics centre's site (fcsc.gov.ae) refused the requests made for "
           "it")
NORTHERN = ("No table of {name}'s population by age and sex could be read for this map: "
            f"{FEDERAL}, and the UAE's open-data portal (bayanat.ae) returned no dataset for "
            "a search for population.")
OTHERS = {
    "Dubai": ("No table of Dubai's population by age and sex could be read for this map. The "
              "Dubai Statistics Center publishes the emirate's population by sex and age "
              "group, but its site (dsc.gov.ae) refused the requests made for it, and no such "
              "table was found among the Internet Archive's copies of the Center's reports."),
    "Sharjah": ("No table of Sharjah's population by age and sex could be read for this map: "
                "the emirate's Department of Statistics and Community Development, which took "
                f"its 2015 census, could not be reached (dscd.sharjah.ae), and {FEDERAL}."),
    "Ajman": NORTHERN.format(name="Ajman"),
    "Fujairah": NORTHERN.format(name="Fujairah"),
    "Ras al-Khaimah": NORTHERN.format(name="Ras al-Khaimah"),
    "Umm al-Quwain": NORTHERN.format(name="Umm al-Quwain"),
}


def read(page: str) -> dict[str, Any]:
    """The emirate and its regions by sex for both years, checked against the text."""
    page = html.unescape(page)
    charts = [(city, int(m), int(f)) for city, m, f in CHART.findall(page)]
    check(len(charts) == 8, f"uae_scad: {len(charts)} population charts, not 8: {charts}")
    emirate = charts[:2]
    regions = charts[2:]
    check([c for c, _m, _f in emirate] == ["AbuDhabi", "AbuDhabi"],
          f"uae_scad: the first two charts are not the emirate's: {emirate}")
    check([c for c, _m, _f in regions] == [r for r in REGIONS for _ in (0, 1)],
          f"uae_scad: the regions' charts are {regions}")
    years = []
    for i in (0, 1):
        men = sum(regions[2 * k + i][1] for k in range(3))
        women = sum(regions[2 * k + i][2] for k in range(3))
        check((men, women) == emirate[i][1:],
              f"uae_scad: the regions make {men:,} men and {women:,} women, the emirate "
              f"{emirate[i][1]:,} and {emirate[i][2]:,}")
        years.append({"men": men, "women": women, "total": men + women,
                      "regions": {regions[2 * k + i][0]: regions[2 * k + i][1]
                                  + regions[2 * k + i][2] for k in range(3)}})
    latest = LATEST.search(page)
    check(latest is not None, "uae_scad: the page states no total for its latest year")
    millions, year = float(latest.group(1)), int(latest.group(2))
    check(year == YEAR, f"uae_scad: the page's latest year is {year}, not {YEAR}")
    now = max(years, key=lambda y: y["total"])
    before = min(years, key=lambda y: y["total"])
    check(round(now["total"] / 1e6, 2) == millions,
          f"uae_scad: {now['total']:,} is not the page's {millions} million in {year}")
    # The latest year's sentence comes first; the earlier year's repeats the
    # regions with its own figures further down the page.
    shares: dict[str, int] = {}
    for name, n in SHARE.findall(page):
        shares.setdefault(name, int(n.replace(",", "")))
    check(shares.get("Al Ain") == now["regions"]["AlAin"]
          and shares.get("Al Dhafra") == now["regions"]["AlDhafra"],
          f"uae_scad: the page's regions {shares} are not the charts' {now['regions']}")
    earlier = EARLIER_TOTAL.search(page)
    check(earlier is not None and round(before["total"] / 1e6, 2) == float(earlier.group(1)),
          f"uae_scad: {before['total']:,} is not the page's {EARLIER} total")
    log(f"  {YEAR}: {now['men']:,} men, {now['women']:,} women ({now['total']:,}); "
        f"{EARLIER}: {before['total']:,}; regions {now['regions']}")
    return {"now": now, "before": before}


def build(figures: dict[str, Any], admin1: list[dict[str, Any]],
          admin2: list[dict[str, Any]]) -> list[dict[str, Any]]:
    found = [u for u in admin1 if u["name"] == DRAWN]
    check(len(found) == 1, f"uae_scad: {len(found)} drawn emirates named {DRAWN}")
    unit = found[0]
    now, before = figures["now"], figures["before"]
    population = measure(now["total"], year=YEAR, source=SOURCE)
    regions = now["regions"]
    population["note"] = (
        f"The Abu Dhabi Census's {YEAR} count from the emirate's integrated administrative "
        f"registers: {now['men']:,} men and {now['women']:,} women, in the regions of Abu "
        f"Dhabi ({regions['AbuDhabi']:,}), Al Ain ({regions['AlAin']:,}) and Al Dhafra "
        f"({regions['AlDhafra']:,}). The revised 2023 census (R1) counted "
        f"{before['total']:,}.")
    rec = record(
        "ARE-SCAD-AbuDhabi", DRAWN, level="admin1", parent=ISO3, country=ISO3,
        match_by="shape_id", shape_id=unit["id"],
        population=population,
        sex_ratio=sex_ratio(now["men"], now["women"], year=YEAR, source=SOURCE),
        sex_ratio_note=(f"Males per 100 females in the census's {YEAR} count: {now['men']:,} "
                        f"men and {now['women']:,} women ({EARLIER}: {before['men']:,} and "
                        f"{before['women']:,})."),
        median_age=gap(NOT_AVAILABLE, AGE_WHY),
        ethnicity=gap(NOT_AVAILABLE, NATIONALITY_WHY),
        religion=gap(NOT_AVAILABLE, RELIGION_WHY),
        language=gap(NOT_AVAILABLE, LANGUAGE_WHY),
        sources=[{"field": "population/sex_ratio", "name": SOURCE, "url": URL, "year": YEAR,
                  "license": LICENCE}])
    rows = [rec]
    for other in admin1:
        if other is unit:
            continue
        why = OTHERS.get(other["name"])
        check(why is not None, f"uae_scad: no reason written for the drawn emirate "
                               f"{other['name']!r}")
        rows.append(record(
            f"ARE-{other['name'].replace(' ', '')}", other["name"], level="admin1",
            parent=ISO3, country=ISO3, match_by="shape_id", shape_id=other["id"],
            median_age=gap(NOT_AVAILABLE, why), sex_ratio=gap(NOT_AVAILABLE, why)))
    rows += second_level_twins(rows, admin2)
    log(f"  {DRAWN}: {now['total']:,} people, {rec['sex_ratio']['value']} men per 100 women; "
        f"written at {sum(1 for r in rows if r['name'] == DRAWN)} level(s); the other "
        f"emirates' reasons at {sum(1 for r in rows if r['name'] != DRAWN)} polygons")
    return rows


def main() -> int:
    argparse.ArgumentParser(description=__doc__,
                            formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    page = http_get(URL, cache=False)
    log(f"  {URL}: {len(page):,} characters")
    rows = build(read(page), units(ISO3, "admin1"), units(ISO3, "admin2"))
    write_json(PROCESSED / OUT, rows)
    log(f"  wrote {OUT} ({len(rows)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
