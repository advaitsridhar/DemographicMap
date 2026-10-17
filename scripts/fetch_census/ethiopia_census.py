#!/usr/bin/env python3
"""Ethiopia: median age and sex ratio for every region and zone, from the 2007 census.

The Central Statistical Agency's 2007 Population and Housing Census is the last
census Ethiopia has completed: the 2017 round was postponed and never held. The
U.S. Census Bureau's subnational workbook for it on HDX (the one ``uscb.py``
reads for religion, ethnicity and language) carries an Age-Sex sheet as well:
everyone by sex and five-year age group, for the country, its thirteen
first-order areas, its zones and its weredas. The map had no median age and no
sex ratio for any of Ethiopia's 11 regions or 74 zones.

**What is written.** For each region and zone polygon: the median age,
interpolated within the five-year group that holds the middle person, and men
per 1,000 women, both from the 2007 count; and the 2007 count itself, which
fills a polygon nothing newer reaches and is held behind any newer figure.

**Checks before anything is written.** Every row's five-year groups make its
total and its sexes make it too; the first-order areas make the country; each
area's zones make the area.

**Which rows make which polygon.** The workbook arranges the 2007 count in the
regions of 2021: Sidama, a zone of the Southern Nations, Nationalities and
Peoples' Region in 2007, is a region of its own, and SNNPR's row is the rest.
The map draws SNNPR as it was before Sidama left it, so its polygon is the two
rows added together, age group by age group, and the map's Sidama zone under
SNNPR is the workbook's Sidama zone. Addis Ababa's ten sub-cities are its
zone-level rows; the map draws one zone-level polygon there ("Region 14"),
which is the region entire.

Special weredas and town administrations were counted apart from the zones
around them. Where the town and the land the census gave it stand inside one
zone polygon, the town's rows are added to that zone's (SPECIAL); the two the
polygons split -- Bahir Dar, on the line between West Gojam and North Gonder,
and Mao-Komo, between Asosa and West Wellega -- are added to neither, and
"Region 17", the workbook's thirteenth first-order area of 96,754 people, which
it does not name, is placed nowhere.

Usage:
    python -m scripts.fetch_census.ethiopia_census
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
from collections import defaultdict
from typing import Any

from . import uscb
from ._shared import PROCESSED, http_get, log, measure, record, write_json
from .binding import fold
from .cod_ps_age import grouped_median

OUT = "ethiopia_census.json"
YEAR = 2007
SITE = PROCESSED.parent.parent / "site" / "data"
NATIONAL = 73_750_932
SOURCE = ("Central Statistical Agency of Ethiopia, 2007 Population and Housing Census, "
          "population by sex and five-year age group, as the U.S. Census Bureau tabulates it "
          "for HDX")
LICENCE = "CC BY-IGO, published via HDX"
GROUP = re.compile(r"^B(\d{2,3})(\d{2,3})$")
OPEN = re.compile(r"^B(\d{2,3})PL$")

# The map's first-level polygon -> the workbook's first-order areas (folded) it holds.
REGIONS = {
    "Addis Ababa": ["adisabeba"],
    "Afar": ["afar"],
    "Amhara": ["amara"],
    "Beneshangul Gumu": ["binshangulgumuz"],
    "Dire Dawa": ["diredawa"],
    "Gambela": ["gambelahizboch"],
    "Hareri": ["harerihizb"],
    "Oromia": ["oromiya"],
    "SNNPR": ["yedebubbiherochbiheresebochnahizboch", "sidama"],
    "Somali": ["sumale"],
    "Tigray": ["tigray"],
}
# A zone polygon's label -> the workbook's zone of another name (folded), in
# the workbook's area(s) that make the polygon's region.
ZONES = {
    "North Shewa(R3)": "northshewa", "North Shewa(R4)": "northshewa",
    "Oromia": "oromiya", "Special Woreda": "argobaspecialwereda", "Majang": "mezhenger",
    "Hareri": "harari", "Kelem Wellega": "kellemwellega",
    "South West Shewa": "southwestshuwa", "KT": "kembatatembaro",
    "Basketo": "basketospecialwereda", "Wolayita": "welayita",
}
# The one zone-level polygon that is a whole first-order area.
WHOLE = {"Region 14": "adisabeba"}
# Special weredas and town administrations counted apart, by the zone polygon
# that holds the town and its land (each placed by the town's coordinates and
# the area around it against the boundary file's polygons).
SPECIAL = {
    "East Shewa": ["adamaspecialwereda"],
    "West Shewa": ["burayuspecialwereda"],
    "Jimma": ["jimmatownspecialwereda"],
    "Southern": ["mekeletownspecialwereda"],
    "Sidama": ["hawassacityadministration"],
    "Metekel": ["pawespecialwereda"],
    "Agnuak": ["etangspecialwereda"],
}
# Counted apart and placed in no polygon, with the reason (logged).
UNPLACED = {
    "bahirdarspecialwereda": "the city lies on the line between West Gojam and North Gonder",
    "maokomospecialwereda": "its land lies across the line between Asosa and West Wellega",
}
# How the census names them, for the notes.
NAMES = {
    "adamaspecialwereda": "Adama", "burayuspecialwereda": "Burayu",
    "jimmatownspecialwereda": "Jimma town", "mekeletownspecialwereda": "Mekele town",
    "hawassacityadministration": "Hawassa city", "pawespecialwereda": "the Pawe special wereda",
    "etangspecialwereda": "the Etang special wereda",
}


def number(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None


def groups_of(row: list[Any], at: dict[str, int]) -> list[tuple[int, int | None, int]]:
    """(from, to, count) for each age group of a row, youngest first; ``to`` None when open."""
    groups = []
    for name, i in at.items():
        closed, open_ = GROUP.match(name), OPEN.match(name)
        if closed:
            groups.append((int(closed.group(1)), int(closed.group(2)), number(row[i]) or 0))
        elif open_:
            groups.append((int(open_.group(1)), None, number(row[i]) or 0))
    return sorted(groups, key=lambda g: g[0])


def missing(row: list[Any], at: dict[str, int]) -> bool:
    """Whether a row carries the workbook's missing marker (a negative count) for its total.

    The Bureau writes -999 where it has no figure for an area, as the religion
    sheet does for four areas; no census reports a negative number of people,
    so any negative total is the marker whatever its value.
    """
    total = number(row[at["BTOTL"]])
    return total is None or total < 0


def area(row: list[Any], at: dict[str, int], where: str) -> dict[str, Any]:
    """One row's count, sexes and age groups, after its sums are checked."""
    groups = groups_of(row, at)
    total, men, women = (number(row[at[k]]) for k in ("BTOTL", "MTOTL", "FTOTL"))
    if not total or men is None or women is None or men < 0 or women < 0:
        raise SystemExit(f"ethiopia_census: {where}: no usable total, male or female count")
    if sum(g[2] for g in groups) != total or men + women != total:
        raise SystemExit(f"ethiopia_census: {where}: groups make {sum(g[2] for g in groups):,}, "
                         f"sexes {men + women:,}, against a total of {total:,}")
    return {"total": total, "men": men, "women": women, "groups": groups}


def added(parts: list[dict[str, Any]]) -> dict[str, Any]:
    """Several areas as one, age group by age group."""
    shape = [(a, b) for a, b, _ in parts[0]["groups"]]
    if any([(a, b) for a, b, _ in p["groups"]] != shape for p in parts):
        raise SystemExit("ethiopia_census: areas with different age groups cannot be added")
    return {"total": sum(p["total"] for p in parts), "men": sum(p["men"] for p in parts),
            "women": sum(p["women"] for p in parts),
            "groups": [(a, b, sum(p["groups"][i][2] for p in parts))
                       for i, (a, b) in enumerate(shape)]}


def parse(rows: list[list[Any]]) -> dict[str, Any]:
    """{"national": area, "regions": {fold: area}, "zones": {(region fold, zone fold): area}},
    with every sum checked."""
    names = ["" if v is None else str(v).strip() for v in rows[0]]
    at = {n: i for i, n in enumerate(names) if n}
    for column in ("ADM_LEVEL", "ADM1_NAME", "ADM2_NAME", "BTOTL", "MTOTL", "FTOTL"):
        if column not in at:
            raise SystemExit(f"ethiopia_census: the Age-Sex sheet has no {column} column")
    out: dict[str, Any] = {"national": None, "regions": {}, "zones": {}, "labels": {},
                           "missing": []}
    for row in rows[2:]:
        level = number(row[at["ADM_LEVEL"]])
        region = str(row[at["ADM1_NAME"]] or "").strip()
        zone = str(row[at["ADM2_NAME"]] or "").strip()
        if level in (0, 1, 2) and missing(row, at):
            # An area the workbook lists without a count: its people, if any,
            # are in its parent's row and its siblings', which the sums below
            # still have to close on.
            out["missing"].append(", ".join(n for n in (region, zone) if n) or "Ethiopia")
            continue
        if level == 0:
            out["national"] = area(row, at, "Ethiopia")
        elif level == 1:
            key = fold(region)
            if key in out["regions"]:
                raise SystemExit(f"ethiopia_census: {region} appears twice")
            out["regions"][key] = area(row, at, region)
            out["labels"][key] = region
        elif level == 2:
            key = (fold(region), fold(zone))
            if key in out["zones"]:
                raise SystemExit(f"ethiopia_census: {region}, {zone} appears twice")
            out["zones"][key] = area(row, at, f"{region}, {zone}")
            out["labels"][key] = zone
    check(out)
    return out


def check(table: dict[str, Any]) -> None:
    if not table["national"] or table["national"]["total"] != NATIONAL:
        raise SystemExit(f"ethiopia_census: the national row is not {NATIONAL:,}")
    made = sum(r["total"] for r in table["regions"].values())
    if made != NATIONAL:
        raise SystemExit(f"ethiopia_census: the first-order areas make {made:,}, not {NATIONAL:,}")
    problems = []
    for key, region in table["regions"].items():
        zones = [z for (r, _), z in table["zones"].items() if r == key]
        for field in ("total", "men", "women"):
            made = sum(z[field] for z in zones)
            if made != region[field]:
                problems.append(f"{table['labels'][key]}'s {len(zones)} zones make {made:,} "
                                f"of its {field}, not {region[field]:,}")
    if problems:
        raise SystemExit("ethiopia_census: " + "; ".join(problems)
                         + f" (listed without a count: {table['missing']})")


def median(figures: dict[str, Any]) -> float | None:
    return grouped_median(figures["groups"])


def fields(figures: dict[str, Any], note: str, of: str = "") -> dict[str, Any]:
    """The record's figures; ``of`` says, for a median, whose ages were added together."""
    out: dict[str, Any] = {
        "population": measure(figures["total"], year=YEAR, source=SOURCE),
        "population_note": note,
        "sex_ratio": measure(round(1000 * figures["men"] / figures["women"]),
                             unit="males_per_1000_females", year=YEAR, source=SOURCE),
        "sources": [{"field": "population/median_age/sex_ratio", "name": SOURCE,
                     "url": uscb.dataset_url(uscb.ETHIOPIA.dataset), "year": YEAR,
                     "license": LICENCE}],
    }
    value = median(figures)
    if value is not None:
        out["median_age"] = measure(value, unit="years", year=YEAR, source=SOURCE)
        out["median_age_note"] = ("Interpolated within the five-year age group that holds the "
                                  "middle person, from the 2007 census's count of everyone by "
                                  f"five-year age group{of}.")
    return out


def plan(table: dict[str, Any], admin1: list[dict[str, Any]], admin2: list[dict[str, Any]]
         ) -> tuple[list[dict[str, Any]], list[str]]:
    """The records, one per polygon, and a report of what went where."""
    records: list[dict[str, Any]] = []
    report: list[str] = []
    labels = table["labels"]
    region_of: dict[str, list[str]] = {}
    for shape in admin1:
        keys = REGIONS.get(shape["name"].strip())
        if not keys or any(k not in table["regions"] for k in keys):
            raise SystemExit(f"ethiopia_census: no first-order area for {shape['name']!r} "
                             f"({keys}); the workbook has {sorted(table['regions'])}")
        region_of[shape["id"]] = keys
        figures = added([table["regions"][k] for k in keys])
        of = ""
        if len(keys) == 1:
            note = "The 2007 census's count for the region."
        else:
            note = ("The 2007 census's counts for the region and for Sidama added up: the region "
                    "is drawn as it was before Sidama Region was made from it in 2020.")
            of = ", of the region and Sidama together"
        records.append(record(f"ETH-2007-{shape['id']}", shape["name"].strip(), level="admin1",
                              parent="ETH", country="ETH", match_by="shape_id",
                              shape_id=shape["id"], **fields(figures, note, of)))
    placed = {"region17"}
    for shape in admin2:
        label = shape["name"].strip()
        regions = region_of.get(shape["parent"], [])
        of = ""
        if label in WHOLE:
            key = WHOLE[label]
            figures = table["regions"][key]
            note = ("The 2007 census's count for Addis Ababa, the whole of which is this one "
                    "polygon.")
            parts = [key]
        else:
            want = ZONES.get(label, fold(label))
            found = [(r, z) for (r, z) in table["zones"] if r in regions and z == want]
            if len(found) != 1:
                report.append(f"{label!r}: {len(found)} zones named {want} in {regions}; "
                              "not written")
                continue
            parts = [found[0]]
            for extra in SPECIAL.get(label, []):
                hits = [(r, z) for (r, z) in table["zones"] if r in regions and z == extra]
                if len(hits) != 1:
                    raise SystemExit(f"ethiopia_census: {extra} not found once in {regions}")
                parts.append(hits[0])
            figures = added([table["zones"][p] for p in parts])
            towns = [NAMES[z] for _, z in parts[1:]]
            if towns:
                note = (f"The 2007 census's count for the zone with {' and '.join(towns)} added: "
                        "the census counted it apart, and this polygon holds it.")
                of = f", of the zone and {' and '.join(towns)} together"
            else:
                note = "The 2007 census's count for the zone."
        placed.update(p if isinstance(p, str) else p[1] for p in parts)
        records.append(record(f"ETH-2007-{shape['id']}", label, level="admin2", parent="ETH",
                              country="ETH", match_by="shape_id", shape_id=shape["id"],
                              **fields(figures, note, of)))
    for key, why in UNPLACED.items():
        report.append(f"{key}: counted apart and placed in no polygon -- {why}")
    left = sorted(labels[k] for k in table["zones"] if k[1] not in placed and k[1] not in UNPLACED
                  and k[0] != "adisabeba")
    report.append(f"zones of the workbook on no polygon: {left}")
    return records, report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", default="", help="a label that tells two dispatches apart; ignored")
    ap.add_argument("--points", action="store_true",
                    help="write points sampled over OCHA's wereda outlines, for placing the "
                         "projection's weredas in the zones drawn")
    args = ap.parse_args()
    if args.points:
        from .uganda_census import write_cod_points  # noqa: PLC0415
        return write_cod_points("cod-ab-eth", 3, "ethiopia_wereda_points.json", 30)
    import openpyxl                                 # noqa: PLC0415
    url = uscb.workbook_url(uscb.ETHIOPIA.dataset)
    blob = http_get(url, binary=True, cache=False, timeout=300)
    log(f"  read {url}: {len(blob):,} bytes, sha256 {hashlib.sha256(blob).hexdigest()}")
    book = openpyxl.load_workbook(io.BytesIO(blob), read_only=True, data_only=True)
    meta = " ".join(str(c) for r in uscb.sheet_rows(book, "Metadata") for c in r if c)
    if str(YEAR) not in meta:
        raise SystemExit(f"ethiopia_census: the workbook's metadata never names {YEAR}")
    table = parse(uscb.sheet_rows(book, "Age-Sex"))
    log(f"  {len(table['regions'])} first-order areas and {len(table['zones'])} zones, making "
        f"{NATIONAL:,}, every row's groups and sexes making its total; listed without a "
        f"count: {table['missing']}")
    admin1 = json.loads((SITE / "admin1" / "ETH.units.json").read_text())
    admin2 = json.loads((SITE / "admin2" / "ETH.units.json").read_text())
    records, report = plan(table, admin1, admin2)
    for line in report:
        log("  " + line)
    by_level = defaultdict(int)
    for r in records:
        by_level[r["level"]] += 1
        log(f"  {r['level']} {r['name']}: {r['population']['value']:,}, median "
            f"{(r.get('median_age') or {}).get('value')}, sex ratio {r['sex_ratio']['value']}")
    log(f"  {by_level['admin1']} of {len(admin1)} regions and {by_level['admin2']} of "
        f"{len(admin2)} zones written")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
