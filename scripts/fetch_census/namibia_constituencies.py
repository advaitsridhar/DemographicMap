#!/usr/bin/env python3
"""Namibia -- the 2023 census's count of the constituencies the map draws as
the census does.

The Namibia Statistics Agency's census site (census.nsa.org.na) gives each
region a page whose first table is "Population by constituency": each 2023
constituency's population, its area in km2 and its density. The fourteen
regions' pages are read; each region's constituencies must make its count in
the census's Main Report (``namibia_census.json``, Table 2.2) exactly, or the
region is left out (Oshikoto's page makes 226,947 against 257,302: Oniipa is
printed 3,372 and Onayena's area "371.47.5").

**Which polygons.** The map draws 103 constituencies of an older delimitation
against the census's 121 (2013, with Kavango split in 2014), under the names
of the constituencies they overlap. A polygon gets the census's count only
where it is the census's ground: its name is the constituency's (or the
constituencies' it is drawn over, ``PARTS``) and its area agrees with the
census's area for them to within 5% -- 2% where more than 500 people live to
the km2, since a sliver of a town is many people. The polygons' areas
(``AREAS``) are measured on the map's own outlines (geoBoundaries CGAZ,
second level, on an equal-area projection), as the runner has no copy of
them. Elsewhere OCHA's 2023 projections stay, and the log says why each
polygon was passed over: Hardap's Gibeon is drawn over 50,525 km2 against the
census's 10,156, Rundu Urban over 16 km2 against 156.

Written: for each polygon that passes, the census's count (two constituencies
added together where the map draws them as one), with the areas in its note.
Nothing else: the region pages give no constituency's sexes or ages.

Usage:
    python -m scripts.fetch_census.namibia_constituencies [--run LABEL]
"""

from __future__ import annotations

import argparse
import html
import json
import re
from typing import Any

from ._shared import PROCESSED, log, measure, record, write_json
from .southern_africa_common import fetch, joined, key, units

SITE_URL = "https://census.nsa.org.na/{slug}/"
ARCHIVE = ("2025", "2024")
SOURCE = ("Namibia Statistics Agency, 2023 Population and Housing Census, regional pages: "
          "population and area by constituency")
LICENCE = "Namibia Statistics Agency publication (reuse with attribution)"
YEAR = 2023
OUT = "namibia_constituencies.json"
REGIONS_FILE = "namibia_census.json"
TOLERANCE = 0.05
DENSE, DENSE_TOLERANCE = 500, 0.02
# The census site's region pages -> the map's first-level unit (reduced): the
# map draws the regions as before 2013 (Kavango whole, Caprivi, Karas).
PAGES = {"kharas-reggion": "karas", "erongo": "erongo", "hardap-region": "hardap",
         "kavango-east-region": "kavango", "kavango-west-region": "kavango",
         "khomas-region": "khomas", "kunene-region": "kunene", "ohangwena-region": "ohangwena",
         "omaheke-region": "omaheke", "omusati-region": "omusati", "oshana-region": "oshana",
         "oshikoto-region": "oshikoto", "otjozondjupa-region": "otjozondjupa",
         "zambezi-region": "caprivi"}
# A polygon's name (reduced) -> the census constituencies it is drawn over,
# where that is not its own name.
PARTS = {"naminusluderitz": ("Nami-Nus",), "okarukambesteinhausen": ("Okorukambe",),
         "rehobothurbaneast": ("Rehoboth East Urban",),
         "rehobothurbanwest": ("Rehoboth West Urban",),
         "karasburg": ("Karasburg East", "Karasburg West"),
         "ondangwa": ("Ondangwa Rural", "Ondangwa Urban"),
         "opuwo": ("Opuwo Rural", "Opuwo Urban"), "kabbe": ("Kabbe North", "Kabbe South"),
         "epukiroandotjinene": ("Epukiro", "Otjinene"),
         "okahaoandotamanzi": ("Okahao", "Otamanzi"),
         "mosesgaroebandtobiashainyeko": ("Moses//Garoeb", "Tobias Hainyeko"),
         "johnpandenisoweto": ("John Pandeni",), "samoramachelwanaheda": ("Samora Machel",),
         "khomasdalnorth": ("Khomasdal",), "eengodi": ("Eengondi",),
         "rundururalwestandrundururaleast": ("Rundu Rural",)}
# Each polygon's area in km2 on the map's outlines (geoBoundaries CGAZ ADM2,
# Lambert cylindrical equal-area on a sphere of 6,371.0088 km), by shape id,
# with the name the map gives it.
AREAS: dict[str, tuple[str, float]] = {
    "8085530B93169958876618": ('Kabbe', 2107.2),
    "8085530B36679342864884": ('Katima Mulilo Rural', 1913.5),
    "8085530B98362387915307": ('Katima Mulilo Urban', 23.2),
    "8085530B65752353592300": ('Kongola', 4962.1),
    "8085530B55251971881937": ('Linyanti', 3796.9),
    "8085530B65700299516233": ('Sibbinda', 1673.4),
    "8085530B4489269593609": ('Arandis', 13523.6),
    "8085530B95120422656670": ('Daures', 17814.8),
    "8085530B40831112301604": ('Karibib', 14574.9),
    "8085530B82641869996514": ('Omaruru', 8450.5),
    "8085530B66062382537531": ('Swakopmund', 191.4),
    "8085530B7908927649027": ('Walvis Bay Rural', 9045.7),
    "8085530B76862246243381": ('Walvis Bay Urban', 16.3),
    "8085530B21041761137658": ('Gibeon', 50525.3),
    "8085530B31527966584052": ('Mariental Rural', 41862.1),
    "8085530B5083436790376": ('Mariental Urban', 5928.7),
    "8085530B57229224453167": ('Rehoboth Rural', 10955.4),
    "8085530B98511433768350": ('Rehoboth Urban East', 283.2),
    "8085530B76307520684232": ('Rehoboth Urban West', 326.5),
    "8085530B58432512744938": ('Berseba', 31826.3),
    "8085530B6128873532004": ('Karasburg', 38321.1),
    "8085530B72153402463843": ('Keetmanshoop Rural', 37948.3),
    "8085530B18943107869251": ('Keetmanshoop Urban', 526.1),
    "8085530B53708494140188": ('Naminus (Luderitz)', 48552.0),
    "8085530B92949915012008": ('Oranjemund', 4271.7),
    "8085530B32015186497374": ('Kahenge', 8805.1),
    "8085530B25496891828693": ('Kapako', 6167.6),
    "8085530B8620298556926": ('Mashare', 9323.1),
    "8085530B94702234009846": ('Mpungu', 8152.3),
    "8085530B20929283489058": ('Mukwe', 5508.8),
    "8085530B15355770078360": ('Ndiyona', 8165.9),
    "8085530B54610932550654": ('Rundu Rural West and Rundu Rural East', 2672.0),
    "8085530B43563455443088": ('Rundu Urban', 16.0),
    "8085530B21626666525774": ('John Pandeni (Soweto)', 1.7),
    "8085530B14647575927701": ('Katutura Central', 2.0),
    "8085530B89449785800632": ('Katutura East', 2.6),
    "8085530B37284584644366": ('Khomasdal North', 27.2),
    "8085530B20678123815895": ('Moses Garoeb and Tobias Hainyeko', 53.2),
    "8085530B18133602337768": ('Samora Machel (Wanaheda)', 18.0),
    "8085530B89251485942037": ('Windhoek East', 166.3),
    "8085530B98123468790734": ('Windhoek Rural', 36687.8),
    "8085530B21115279839445": ('Windhoek West', 208.8),
    "8085530B22817076083997": ('Epupa', 23772.3),
    "8085530B32038896261798": ('Kamanjab', 17166.7),
    "8085530B13904608140223": ('Khorixas', 21345.4),
    "8085530B1397183935319": ('Opuwo', 25817.0),
    "8085530B46481939824826": ('Outjo', 7489.3),
    "8085530B13849316712555": ('Sesfontein', 20243.9),
    "8085530B97832034591555": ('Eenhana', 1276.7),
    "8085530B41372422765993": ('Endola and part of Omulonga', 491.8),
    "8085530B71951838310116": ('Engela', 296.5),
    "8085530B70174010511027": ('Epembe', 1814.3),
    "8085530B38613626402367": ('Ohangwena', 171.1),
    "8085530B24571468385380": ('Okongo', 4616.6),
    "8085530B80005725357017": ('Omundaungilo', 590.2),
    "8085530B82920492062814": ('Ondobe and part of Omulonga', 724.2),
    "8085530B89628533476964": ('Ongenga', 318.1),
    "8085530B86358564716630": ('Oshikango', 299.2),
    "8085530B99967459271040": ('Aminius', 12998.8),
    "8085530B69443629768018": ('Epukiro and Otjinene', 17509.6),
    "8085530B19115739893347": ('Gobabis', 5679.3),
    "8085530B48440603046633": ('Kalahari', 12250.1),
    "8085530B9685426403450": ('Okarukambe (Steinhausen)', 17539.4),
    "8085530B6769010306360": ('Otjombinde', 18939.9),
    "8085530B14721673069070": ('Part of Kalahari', 0.4),
    "8085530B69657715980270": ('Anamulenge', 355.1),
    "8085530B29689182675065": ('Elim', 609.0),
    "8085530B20756190714090": ('Etayi', 644.8),
    "8085530B13053128018864": ('Ogongo', 811.3),
    "8085530B45800656358719": ('Okahao and Otamanzi', 13961.8),
    "8085530B61010853817860": ('Okalongo', 656.5),
    "8085530B26266380145337": ('Onesi', 603.6),
    "8085530B50000229665639": ('Oshikuku', 277.7),
    "8085530B58206281674272": ('Outapi', 986.7),
    "8085530B60954299399074": ('Ruacana', 5383.0),
    "8085530B5370186300175": ('Tsandi', 2365.5),
    "8085530B99858468044406": ('Okaku', 243.6),
    "8085530B80313006361884": ('Okatana', 428.0),
    "8085530B22414954750771": ('Okatyali', 558.5),
    "8085530B50229132451549": ('Ompundja', 468.9),
    "8085530B33910100855161": ('Ondangwa', 209.1),
    "8085530B77309525155932": ('Ongwediva', 203.6),
    "8085530B97751142131458": ('Oshakati East', 187.4),
    "8085530B72164373326164": ('Oshakati West', 241.4),
    "8085530B9301537631137": ('Uukwiyu', 299.7),
    "8085530B68300623753750": ('Uuvudhiya', 5838.3),
    "8085530B29258054008040": ('Eengodi', 7827.5),
    "8085530B91972581324678": ('Guinas', 10240.3),
    "8085530B77479580509837": ('Okankolo', 3562.9),
    "8085530B69947068082144": ('Olukonda', 241.9),
    "8085530B62166928705780": ('Omuntele', 1805.9),
    "8085530B46277296782618": ('Omuthiyagwiipundi', 13432.4),
    "8085530B1263829069027": ('Onayena', 443.4),
    "8085530B69734466281128": ('Oniipa', 373.3),
    "8085530B83100198337410": ('Onyaanya', 560.0),
    "8085530B13094977387263": ('Tsumeb', 273.1),
    "8085530B89384563717914": ('Grootfontein', 11299.3),
    "8085530B47244419743563": ('Okahandja', 5893.3),
    "8085530B39960137622469": ('Okakarara', 14682.8),
    "8085530B51298559628013": ('Omatako', 26222.5),
    "8085530B12011359308575": ('Otavi', 12995.7),
    "8085530B9471970817633": ('Otjiwarongo', 5930.4),
    "8085530B50701756116160": ('Tsumkwe', 27909.6),
}
ATTR = re.compile(r"""data-chart_data\s*=\s*(?:'([^']*)'|"([^"]*)")""")


def number(text: Any) -> float:
    """'17 243', ' 48 270.82' -> the number; the site writes thousands with spaces."""
    clean = re.sub(r"\s", "", str(text))
    if not re.fullmatch(r"\d+(?:\.\d+)?", clean):
        raise ValueError(f"not a number: {text!r}")
    return float(clean)


def tables(page: str) -> list[dict[str, Any]]:
    """Every chart table on a page: its column titles and rows."""
    out = []
    for single, double in ATTR.findall(page):
        try:
            obj = json.loads(html.unescape(single or double))
        except ValueError:
            continue
        if not isinstance(obj, dict) or not isinstance(obj.get("data"), list):
            continue
        cols = [c.get("title") if isinstance(c, dict) else c for c in obj.get("columns") or []]
        out.append({"columns": cols, "rows": obj["data"]})
    return out


def constituencies(page: str) -> dict[str, dict[str, Any]]:
    """{constituency (reduced): {"name", "population", "area"}} from the page's
    first table of population and area by constituency; an area the page
    misprints is None."""
    for table in tables(page):
        cols = [str(c or "").strip().lower() for c in table["columns"]]
        if len(cols) < 3 or cols[:2] != ["constituency", "population"] \
                or not cols[2].startswith("area"):
            continue
        out = {}
        for row in table["rows"]:
            name = " ".join(str(row[0]).split())
            try:
                area: float | None = number(row[2])
            except ValueError:
                area = None
            out[key(name)] = {"name": name, "population": int(number(row[1])), "area": area}
        return out
    raise SystemExit("namibia_constituencies: no table of population by constituency")


def region_totals() -> dict[str, int]:
    """The census's count of each of the map's regions (reduced name), as the
    Main Report's Table 2.2 gives it."""
    rows = json.loads((PROCESSED / REGIONS_FILE).read_text(encoding="utf-8"))
    return {key(r["name"]): r["population"]["value"] for r in rows
            if r.get("level") == "admin1" and isinstance(r.get("population"), dict)
            and "value" in r["population"]}


def checked(pages: dict[str, dict[str, dict[str, Any]]],
            totals: dict[str, int]) -> dict[str, dict[str, dict[str, Any]]]:
    """{region: {constituency: row}} for the regions whose constituencies make
    the region's census count exactly; the others are logged and left out."""
    by_region: dict[str, dict[str, dict[str, Any]]] = {}
    for slug, rows in pages.items():
        by_region.setdefault(PAGES[slug], {}).update(rows)
    good = {}
    for region, rows in sorted(by_region.items()):
        made = sum(r["population"] for r in rows.values())
        if made != totals.get(region):
            log(f"  {region}: the constituencies make {made:,} against the census's "
                f"{totals.get(region)}; left out")
            continue
        good[region] = rows
    return good


def build(regions: dict[str, dict[str, dict[str, Any]]], admin1: list[dict[str, Any]],
          admin2: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """A record for each polygon that is the census's ground, citing the page
    its constituencies' rows were read from (Kavango East's or Kavango
    West's, not both)."""
    parents = {u["id"]: key(u["name"]) for u in admin1}
    out = []
    for shape in sorted(admin2, key=lambda u: u["name"]):
        region = parents.get(shape.get("parent"), "")
        rows = regions.get(region)
        k = key(shape["name"])
        if rows is None:
            log(f"    {shape['name']}: its region's figures are left out")
            continue
        wanted = PARTS.get(k, (shape["name"],))
        parts = [rows.get(key(w)) for w in wanted]
        drawn = AREAS.get(shape["id"], (None, None))[1]
        if None in parts or drawn is None:
            log(f"    {shape['name']}: no constituency of the census by that name ({wanted})")
            continue
        if any(p["area"] is None for p in parts):
            log(f"    {shape['name']}: the census's area is misprinted")
            continue
        area = sum(p["area"] for p in parts)
        people = sum(p["population"] for p in parts)
        allowed = DENSE_TOLERANCE if people / area > DENSE else TOLERANCE
        if abs(drawn / area - 1) > allowed:
            log(f"    {shape['name']}: drawn over {drawn:,.1f} km2 against the census's "
                f"{area:,.1f}; left out")
            continue
        names = [p["name"] for p in parts]
        what = (f"{names[0]} constituency" if len(names) == 1
                else f"{joined(names)} constituencies")
        areas = (f"{area:,.0f} km² in the census's table{'s' if len(names) > 1 else ''}, "
                 f"{drawn:,.0f} km² as the map draws it")
        if len(names) > 1:
            note = (f"The 2023 census's counts for {what} added together: the map draws them "
                    f"as one ({areas}).")
        elif key(names[0]) != k:
            note = f"The 2023 census's count for {what}, drawn here as {shape['name']} ({areas})."
        else:
            note = f"The 2023 census's count for {what} ({areas})."
        out.append(record(
            f"NAM-2023-constituency-{shape['id']}", shape["name"], level="admin2", parent="NAM",
            country="NAM", match_by="shape_id", shape_id=shape["id"],
            sources=[{"field": "population", "name": SOURCE, "url": u, "license": LICENCE,
                      "year": YEAR} for u in dict.fromkeys(p["url"] for p in parts)],
            population=measure(people, year=YEAR, source=SOURCE), population_note=note))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", help="a label that tells one dispatch from another; not used")
    parser.parse_args()
    pages: dict[str, dict[str, dict[str, Any]]] = {}
    for slug in PAGES:
        url = SITE_URL.format(slug=slug)
        body, where = fetch(url, archive=ARCHIVE)
        rows = constituencies(body.decode("utf-8", "replace"))
        log(f"  {slug}: {len(rows)} constituencies, "
            f"{sum(r['population'] for r in rows.values()):,} people ({where})")
        pages[slug] = {k: {**row, "url": url} for k, row in rows.items()}
    regions = checked(pages, region_totals())
    records = build(regions, units("NAM", "admin1"), units("NAM", "admin2"))
    for r in records:
        log(f"  {r['name']}: {r['population']['value']:,} -- {r['population_note']}")
    log(f"  {len(records)} of {len(AREAS)} polygons given the census's count")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
