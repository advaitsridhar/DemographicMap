#!/usr/bin/env python3
"""Djibouti: the 2024 census's head count and men and women by region, and why
nothing else is written.

Djibouti's third general census of population and housing (RGPH-3) counted
1,066,809 people on 20 May 2024. The national institute's results by region and
sub-prefecture are tabulated by City Population (citypopulation.de, Thomas
Brinkhoff), which is read here: the index page's five regions, the city of
Djibouti (a region of its own), the sub-prefectures and towns within each
region and the national row; and each region's own page, which gives its men
and women ("Gender (C 2024)").

**Regions.** Each region's 2024 count, and its men per 1,000 women from its
page's men and women, which must make the count already read. The map carried
English Wikipedia's figures, among them 776,966 for the city of Djibouti, which
with the other five regions' counts makes 9,716 more than the national total,
and Obock's 37,856 of 2009.

**The second level.** The map's eleven units in Djibouti are an older division
than the 2024 sub-prefectures (Arta Region has none of its own, and the unit
named Djibouti holds the city and Balbala with the town of Arta and the land
between), and the census publishes no outlines, so whether a unit is a
sub-prefecture of 2024, or which of them make it up, is not established: each
says why it carries no count and no sex ratio. That includes Ali Sabeh, which
is not Ali Sabieh region's ground as the map draws the region: its polygon
(about 2,150 km2) is larger than the region's (about 1,830 km2), and some 390
km2 of it lie outside the region's polygon.

**Ages** are published for no region: every unit says so.

**Checks.** The regions make the national total, each region's sub-prefectures
and towns make the region, and each region's men and women make its count.

Usage:
    python -m scripts.fetch_census.djibouti_census
"""

from __future__ import annotations

import argparse
import html as html_lib
import json
import re
import urllib.parse
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, gap, http_get, log, measure, record, write_json
from .binding import fold
from .cited_sources import Tables, count, main_name

OUT = "djibouti_census.json"
YEAR = 2024
NATIONAL = 1_066_809
SITE = PROCESSED.parent.parent / "site" / "data"
URL = "https://www.citypopulation.de/en/djibouti/admin/"
SOURCE = ("Institut National de la Statistique de Djibouti, Third General Census of Population "
          "and Housing (RGPH-3), 20 May 2024, as City Population (citypopulation.de) tabulates "
          "it")
LICENCE = "citation of citypopulation.de required"
AGES = ("No count of people by age below the country has been found in the 2024 census's "
        "results, which so far give head counts and men and women by region and "
        "sub-prefecture.")
UNITS = ("The 2024 census was published for Djibouti's regions and its sub-prefectures of "
         "2024, without their outlines, and whether this unit as drawn is one of them, or "
         "which of them make it up, is not established, so no count is given for it.")
SEXES = ("The 2024 census gives men and women for Djibouti's regions and its sub-prefectures "
         "of 2024, without their outlines, and whether this unit as drawn is one of them, or "
         "which of them make it up, is not established, so no sex ratio is given for it.")
# A region's page: /en/djibouti/admin/<number>__<name>/ on the index page.
HREF = re.compile(r"""href=["']([^"']+)["']""")
REGION_LINK = re.compile(r"/djibouti/admin/\d+__([^/]+)/?$")
GENDER = re.compile(r"Gender \(C 2024\)\s*Males\s*([\d,]+)\s*Females\s*([\d,]+)")


def read_table(html: str) -> dict[str, Any]:
    """{"regions": {key: {name, total, parts}}} from the index page, checked."""
    parser = Tables()
    parser.feed(html)
    table = next((t for t in parser.tables
                  if any("Census 2024" in c for r in t[:2] for c in r)), None)
    if table is None:
        raise SystemExit("djibouti_census: no table on the page has a 2024 census column")
    head = next(r for r in table if any("Census 2024" in c for c in r))
    col = next(i for i, c in enumerate(head) if "Census 2024" in c)
    name_col = next(i for i, c in enumerate(head) if c.strip().lower() == "name")
    status_col = next(i for i, c in enumerate(head) if c.strip().lower() == "status")
    regions: dict[str, dict[str, Any]] = {}
    current = None
    national = None
    for row in table:
        if len(row) <= col or row is head:
            continue
        name, status, figure = main_name(row[name_col]), row[status_col].strip(), count(row[col])
        if figure is None:
            continue
        if status == "Republic":
            national = figure
        elif status == "Region":
            current = regions.setdefault(fold(name), {"name": name, "total": figure, "parts": 0})
        elif status == "City" and fold(name) == "djibouti":
            # The city is a region of its own; its communes follow it.
            current = regions.setdefault("djibouti", {"name": name, "total": figure, "parts": 0})
        elif current is not None:
            current["parts"] += figure
    if national != NATIONAL:
        raise SystemExit(f"djibouti_census: the national row is {national}, not {NATIONAL:,}")
    made = sum(r["total"] for r in regions.values())
    if len(regions) != 6 or made != NATIONAL:
        raise SystemExit(f"djibouti_census: {len(regions)} regions making {made:,}")
    for r in regions.values():
        if r["parts"] != r["total"]:
            raise SystemExit(f"djibouti_census: {r['name']}'s parts make {r['parts']:,}, not "
                             f"{r['total']:,}")
    return {"regions": regions}


def region_pages(html: str) -> dict[str, str]:
    """{region key: its page's URL} from the index page's links."""
    out: dict[str, str] = {}
    for href in HREF.findall(html):
        url = urllib.parse.urljoin(URL, html_lib.unescape(href))
        found = REGION_LINK.search(url)
        if found:
            key = fold(urllib.parse.unquote(found.group(1)).replace("_", " "))
            out.setdefault(key, url if url.endswith("/") else url + "/")
    return out


def read_sexes(page: str, region: dict[str, Any]) -> tuple[int, int]:
    """(men, women) from a region's page, which must make the region's count."""
    text = " ".join(re.sub(r"(?is)<(script|style).*?</\1>|<[^>]+>", " ",
                           html_lib.unescape(page)).split())
    found = GENDER.search(text)
    if found is None:
        raise SystemExit(f"djibouti_census: {region['name']}'s page gives no men and women")
    men, women = (count(g) for g in found.groups())
    if men is None or women is None or men + women != region["total"]:
        raise SystemExit(f"djibouti_census: {region['name']}: {men} men and {women} women "
                         f"against a count of {region['total']:,}")
    return men, women


def build(table: dict[str, Any], admin1: list[dict[str, Any]],
          admin2: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ages = gap(NOT_AVAILABLE, AGES)
    records = []
    for shape in admin1:
        key = fold(shape["name"])
        row = table["regions"].get(key)
        if row is None:
            raise SystemExit(f"djibouti_census: no 2024 count for {shape['name']}")
        city = key == "djibouti"
        fields: dict[str, Any] = {
            "population": measure(row["total"], year=YEAR, source=SOURCE),
            "population_note": ("The 2024 census's count of everyone in the region." if not city
                                else "The 2024 census's count of everyone in the city of "
                                     "Djibouti, a region of its own."),
            "median_age": ages}
        cite = [{"field": "population", "name": SOURCE, "url": URL, "year": YEAR,
                 "license": LICENCE},
                {"field": "median_age note", "name": SOURCE, "url": URL, "year": YEAR,
                 "license": LICENCE}]
        if row.get("men") is not None:
            fields["sex_ratio"] = measure(round(1000 * row["men"] / row["women"]),
                                          unit="males_per_1000_females", year=YEAR,
                                          source=SOURCE)
            fields["sex_ratio_note"] = (
                f"Men per 1,000 women in the 2024 census's count of the "
                f"{'city' if city else 'region'}: {row['men']:,} men and {row['women']:,} "
                "women.")
            cite.append({"field": "sex_ratio", "name": SOURCE,
                         "url": row.get("page") or URL, "year": YEAR, "license": LICENCE})
        else:
            fields["sex_ratio"] = gap(NOT_AVAILABLE, AGES)
            cite[1]["field"] = "median_age note/sex_ratio note"
        records.append(record(
            f"DJI-2024-{shape['id']}", shape["name"].strip(), level="admin1", parent="DJI",
            country="DJI", match_by="shape_id", shape_id=shape["id"], sources=cite, **fields))
    for shape in admin2:
        records.append(record(
            f"DJI-2024-{shape['id']}", shape["name"].strip(), level="admin2", parent="DJI",
            country="DJI", match_by="shape_id", shape_id=shape["id"],
            population=gap(NOT_AVAILABLE, UNITS), median_age=ages,
            sex_ratio=gap(NOT_AVAILABLE, SEXES),
            sources=[{"field": "population note/median_age note/sex_ratio note", "name": SOURCE,
                      "url": URL, "year": YEAR, "license": LICENCE}]))
    return records


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", default="", help="a label that tells two dispatches apart; ignored")
    ap.parse_args()

    def get(url: str) -> str:
        body = http_get(url, cache=False, timeout=120)
        return body if isinstance(body, str) else body.decode("utf-8", "replace")

    html = get(URL)
    table = read_table(html)
    pages = region_pages(html)
    for key, region in table["regions"].items():
        url = pages.get(key)
        if url is None:
            raise SystemExit(f"djibouti_census: no page linked for {region['name']}: "
                             f"{sorted(pages)}")
        region["men"], region["women"] = read_sexes(get(url), region)
        region["page"] = url
        log(f"  {region['name']}: {region['total']:,}, its parts making it; {region['men']:,} "
            f"men and {region['women']:,} women ({url})")
    admin1 = json.loads((SITE / "admin1" / "DJI.units.json").read_text())
    admin2 = json.loads((SITE / "admin2" / "DJI.units.json").read_text())
    records = build(table, admin1, admin2)
    write_json(PROCESSED / OUT, records)
    log(f"  {len(admin1)} regions and {len(admin2)} second-level units written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
