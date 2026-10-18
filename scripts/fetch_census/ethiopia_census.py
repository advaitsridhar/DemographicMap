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
zone polygon, the town's rows are added to that zone's (SPECIAL), Mao-Komo's to
Asosa's (OCHA's outline of it lies 94% in the Asosa polygon); Bahir Dar, whose
centre lies on the line between West Gojam and North Gonder, is added to
neither, and both zones' notes say so. "Region 17", the workbook's thirteenth
first-order area of 96,754 people, which it does not name, is placed nowhere.

**The newer head count** (``ethiopia_projection.json``). The statistics office
(the Central Statistical Agency, since 2021 the Ethiopian Statistics Service)
projects the 2007 count forward by region, zone and wereda; OCHA's COD-PS for
Ethiopia tabulates the projection for July 2022. Its regions are the map's,
with SNNPR the sum of SNNP, Sidama and South West Ethiopia, the regions made
from it in 2020 and 2021. Its zones are today's, and several of them are not
the map's 2007 zones (Bale without East Bale, North Gondar without Central and
West Gondar, the Somali region's new weredas across the old zone lines), so a
zone polygon takes the sum of the weredas that lie within it, from the
placement in ``ethiopia_zones`` (OCHA's wereda outlines against the polygons).
A zone's sum is written where it is the zone's ground but for slivers: the
parts of the weredas that straddle its line lying more than 2 km across it
(``ethiopia_zones.SHARES``; nearer the line, two drawings of it disagree) are
no more than one in twenty, both the zone's ground the sum leaves out and the
ground beyond its line the sum takes in, counted either in people (each
wereda's people spread evenly over its outline) or in area (the outlines'
areas). Each count is coarse where the other is not (one sampled point of a
populous wereda weighs heavily against a sparse zone's people, but little
against its area), so a sum within the bound by either count is written, and
its note names any straddling wereda whose part, counted in people, is more
than one in two hundred of the sum. A zone whose weredas the table and the
outlines do not both know is left to the 2007 count. (OCHA's own zone table is
by the zones of 2022, and where one of them is a drawn zone's ground, its
weredas are that zone's sum here.) The projection's sex and age split are not
read: a census's own figure stands over a projection's, and the table applies
one age structure to all the weredas of a zone.

Usage:
    python -m scripts.fetch_census.ethiopia_census
    python -m scripts.fetch_census.ethiopia_census --points
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
from collections import defaultdict
from difflib import SequenceMatcher
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
    # OCHA's outline of the Mao-Komo special wereda lies 94% in the Asosa
    # polygon (6% in West Wellega's), and the projection's Asosa holds it too.
    "Asosa": ["maokomospecialwereda"],
}
# Counted apart and placed in no polygon, with the reason (logged), and the
# zone polygons whose notes say so: Bahir Dar's centre lies 0.3 km inside
# North Gonder's polygon, while OCHA's outline of the town lies 81% in West
# Gojam's.
UNPLACED = {
    "bahirdarspecialwereda": "the city lies on the line between West Gojam and North Gonder",
}
UNPLACED_ON = {"bahirdarspecialwereda": ("West Gojam", "North Gonder")}
# How the census names them, for the notes.
NAMES = {
    "adamaspecialwereda": "Adama", "burayuspecialwereda": "Burayu",
    "jimmatownspecialwereda": "Jimma town", "mekeletownspecialwereda": "Mekele town",
    "hawassacityadministration": "Hawassa city", "pawespecialwereda": "the Pawe special wereda",
    "etangspecialwereda": "the Etang special wereda",
    "maokomospecialwereda": "the Mao-Komo special wereda", "bahirdarspecialwereda": "Bahir Dar",
}
# Seats the map's sources give for none of these: the two chartered cities,
# whose seat is the city itself, at both levels (each is drawn as one zone too),
# Harari Region drawn as one zone, and SNNPR as drawn, whose seat was Hawassa.
# {(level, polygon label): (seat, note, the source cited for it)}.
WIKIDATA = "https://www.wikidata.org/wiki/"
SNNPR_ARTICLE = ("https://en.wikipedia.org/wiki/"
                 "Southern_Nations,_Nationalities,_and_Peoples%27_Region")
CAPITALS: dict[tuple[str, str], tuple[str, str, dict[str, str]]] = {
    ("admin1", "Addis Ababa"): (
        "Addis Ababa", "Addis Ababa is a chartered city, whose seat is the city itself.",
        {"name": "Wikidata", "url": WIKIDATA + "Q3624", "license": "CC0"}),
    ("admin2", "Region 14"): (
        "Addis Ababa", "Addis Ababa, a chartered city, is drawn as this one zone; its seat is "
                       "the city itself.",
        {"name": "Wikidata", "url": WIKIDATA + "Q3624", "license": "CC0"}),
    ("admin1", "Dire Dawa"): (
        "Dire Dawa", "Dire Dawa is a chartered city, whose seat is the city itself.",
        {"name": "Wikidata", "url": WIKIDATA + "Q193486", "license": "CC0"}),
    ("admin2", "Dire Dawa"): (
        "Dire Dawa", "Dire Dawa, a chartered city, is drawn as this one zone; its seat is the "
                     "city itself.",
        {"name": "Wikidata", "url": WIKIDATA + "Q193486", "license": "CC0"}),
    ("admin2", "Hareri"): (
        "Harar", "Harari Region is drawn as this one zone; its seat is Harar.",
        {"name": "Wikidata", "url": WIKIDATA + "Q1033855", "license": "CC0"}),
    ("admin1", "SNNPR"): (
        "Hawassa", "Hawassa was the region's seat until the region was divided in 2023; it is "
                   "drawn here as it was before Sidama Region, which holds Hawassa, was made "
                   "from it in 2020.",
        {"name": "English Wikipedia, Southern Nations, Nationalities, and Peoples' Region",
         "url": SNNPR_ARTICLE, "license": "CC BY-SA 4.0"}),
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


def seated(level: str, label: str, out: dict[str, Any]) -> dict[str, Any]:
    """``out`` with the polygon's seat from CAPITALS, where it has one there."""
    seat = CAPITALS.get((level, label))
    if seat is None:
        return out
    capital, note, source = seat
    return {**out, "capital": capital, "capital_note": note,
            "sources": [*out["sources"], {"field": "capital", **source}]}


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
                              shape_id=shape["id"],
                              **seated("admin1", shape["name"].strip(),
                                       fields(figures, note, of))))
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
                        "the census counted it apart, and it lies within the zone as drawn.")
                of = f", of the zone and {' and '.join(towns)} together"
            else:
                note = "The 2007 census's count for the zone."
        without = []
        for apart, zones in UNPLACED_ON.items():
            if label not in zones:
                continue
            hits = [(r, z) for (r, z) in table["zones"] if r in regions and z == apart]
            if len(hits) != 1:
                raise SystemExit(f"ethiopia_census: {apart} not found once in {regions}")
            other = next(z for z in zones if z != label)
            note += (f" {NAMES[apart]}, which the census counted apart "
                     f"({table['zones'][hits[0]]['total']:,} people), is in neither this "
                     f"figure nor {other}'s: the city lies on the line between the two zones "
                     f"as drawn, most of its area in {zones[0]}.")
            without.append(NAMES[apart])
        out = fields(figures, note, of + "".join(f", without {w}, which the census counted apart"
                                                 for w in without))
        if without:
            out["sex_ratio_note"] = (f"From the 2007 census's count of the zone's men and women, "
                                     f"without {' and '.join(without)}, which the census counted "
                                     "apart.")
        placed.update(p if isinstance(p, str) else p[1] for p in parts)
        records.append(record(f"ETH-2007-{shape['id']}", label, level="admin2", parent="ETH",
                              country="ETH", match_by="shape_id", shape_id=shape["id"],
                              **seated("admin2", label, out)))
    for key, why in UNPLACED.items():
        report.append(f"{key}: counted apart and placed in no polygon -- {why}")
    left = sorted(labels[k] for k in table["zones"] if k[1] not in placed and k[1] not in UNPLACED
                  and k[0] != "adisabeba")
    report.append(f"zones of the workbook on no polygon: {left}")
    return records, report


PROJECTION_OUT = "ethiopia_projection.json"
# The projection's weredas as read, each with the outline and the zone polygon
# it was placed in, for checking.
PROJECTION_WEREDAS = "ethiopia_projection_weredas.json"
# Points sampled over OCHA's wereda outlines, with each outline's area (--points).
WEREDA_POINTS = "ethiopia_wereda_points.json"
# How many of a zone's people may lie in weredas straddling its line, either
# way, and how many a straddling wereda must bring in to be named.
SLIVER = 0.05
NAMED = 0.005
# A wereda whose code is the outline's, in a region whose codes were not
# reissued, with a name this alike (Kelete Awelallo, Kilte Awulaelo).
ALIKE = 0.7
REISSUED = {"ET07", "ET08", "ET11", "ET16"}
PROJECTION_YEAR = 2022
PROJECTION_DATASET = "cod-ps-eth"
PROJECTION_SOURCE = ("Ethiopian Statistics Service, population projection for July 2022 from the "
                     "2007 census, by region, zone and wereda, as OCHA's COD-PS tabulates it")
# The map's region -> the projection's regions (folded) it holds.
PROJECTION_REGIONS = {
    "Addis Ababa": ["addisababa"], "Afar": ["afar"], "Amhara": ["amhara"],
    "Beneshangul Gumu": ["benishangulgumz"], "Dire Dawa": ["diredawa"], "Gambela": ["gambela"],
    "Hareri": ["harari"], "Oromia": ["oromia"],
    "SNNPR": ["snnp", "sidama", "southwestethiopia"], "Somali": ["somali"],
    "Tigray": ["tigray"],
}


def projection_tables() -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], str]:
    """The projection's regions {fold: row} and weredas {pcode: row}, and the dataset page."""
    resources = uscb.package(PROJECTION_DATASET).get("resources", [])

    def table(pattern: str) -> list[dict[str, str]]:
        hits = [r for r in resources if re.search(pattern, str(r.get("name") or ""), re.I)]
        if len(hits) != 1:
            raise SystemExit(f"ethiopia_census: {len(hits)} resources match {pattern}")
        body = http_get(hits[0]["url"], cache=False, timeout=300)
        text = body if isinstance(body, str) else body.decode("utf-8-sig", "replace")
        log(f"  read {hits[0]['url']}: {len(text):,} characters")
        import csv                                  # noqa: PLC0415
        return list(csv.DictReader(io.StringIO(text.lstrip("﻿"))))

    def count(row: dict[str, str], key: str) -> int:
        return int(float(str(row.get(key) or "0").replace(",", "")))

    regions = {}
    for row in table(r"adm1_2022_v2\.csv$"):
        total, men, women = (count(row, k) for k in ("T_TL", "M_TL", "F_TL"))
        # The projection's cells are rounded one by one: a person either way.
        if abs(men + women - total) > 2:
            raise SystemExit(f"ethiopia_census: {row['admin1Name_en']}: sexes make "
                             f"{men + women:,}, not {total:,}")
        regions[fold(row["admin1Name_en"])] = {"name": row["admin1Name_en"], "total": total}
    weredas = {}
    for row in table(r"adm3_2022_v2\.csv$"):
        weredas[row["admin3Pcode"]] = {"name": row["admin3Name_en"], "zone": row["admin2Pcode"],
                                       "total": count(row, "T_TL")}
    made = sum(w["total"] for w in weredas.values())
    national = sum(r["total"] for r in regions.values())
    if abs(made - national) > national * 0.001:
        raise SystemExit(f"ethiopia_census: the projection's weredas make {made:,}, its regions "
                         f"{national:,}")
    return regions, weredas, uscb.dataset_url(PROJECTION_DATASET)


# The outlines' region codes a projection wereda's may have become: Tigray's
# western weredas are ET99 in the outlines; SNNPR's (ET07) went to Sidama (ET16),
# South West Ethiopia (ET11) and South Ethiopia (ET08), and kept ET07 in Central.
REGION_FAMILY = {"ET01": {"ET01", "ET99"}, "ET07": {"ET07", "ET08", "ET11", "ET16"}}
# Zones the map draws that are a whole region: {zone label: projection regions}.
PROJECTION_WHOLE = {"Region 14": ["addisababa"], "Dire Dawa": ["diredawa"],
                    "Hareri": ["harari"]}
# The projection's region codes within each region the map draws.
REGION_CODES = {"Tigray": {"ET01"}, "Afar": {"ET02"}, "Amhara": {"ET03"}, "Oromia": {"ET04"},
                "Somali": {"ET05"}, "Beneshangul Gumu": {"ET06"},
                "SNNPR": {"ET07", "ET11", "ET16"}, "Gambela": {"ET12"}, "Hareri": {"ET13"},
                "Addis Ababa": {"ET14"}, "Dire Dawa": {"ET15"}}


def bare(name: str) -> str:
    """A wereda's name without a special wereda's label or a bracketed region. A town
    keeps its "town": it is not the wereda around it."""
    text = re.sub(r"\(.*?\)", " ", name.lower())
    text = re.sub(r"\b(special|sp|woreda|wereda)\b", " ", text)
    return fold(text)


def listed(names: list[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def projection_records(regions: dict[str, dict[str, Any]], weredas: dict[str, dict[str, Any]],
                       page: str, admin1: list[dict[str, Any]], admin2: list[dict[str, Any]],
                       areas: dict[str, float] | None = None
                       ) -> tuple[list[dict[str, Any]], list[str]]:
    """The projection's records; ``areas`` gives each wereda outline's area in km2."""
    from .ethiopia_zones import NAMES, PLACED, SHARES  # noqa: PLC0415
    areas = areas or {}
    cite = [{"field": "population", "name": PROJECTION_SOURCE, "url": page,
             "year": PROJECTION_YEAR, "license": LICENCE}]
    records, report = [], []
    for shape in admin1:
        keys = PROJECTION_REGIONS[shape["name"].strip()]
        if any(k not in regions for k in keys):
            raise SystemExit(f"ethiopia_census: the projection has no {keys}: {sorted(regions)}")
        total = sum(regions[k]["total"] for k in keys)
        note = ("The statistics office's projection for July 2022, from the 2007 census."
                if len(keys) == 1 else
                "The statistics office's projections for July 2022 for SNNP, Sidama and South "
                "West Ethiopia added up: the region is drawn as it was before Sidama (2020) and "
                "South West Ethiopia (2021) were made from it.")
        records.append(record(f"ETH-2022-{shape['id']}", shape["name"].strip(), level="admin1",
                              parent="ETH", country="ETH", match_by="shape_id",
                              shape_id=shape["id"],
                              population=measure(total, year=PROJECTION_YEAR,
                                                 source=PROJECTION_SOURCE),
                              population_note=note, sources=cite))
    # The projection's wereda codes are those of 2021; the outlines' are later,
    # and the regions made from SNNPR in 2023 recoded its weredas. A wereda is
    # its outline where the two share a code and a name, else the one outline
    # of its name not taken by another.
    home = {c: sid for sid, codes in PLACED.items() for c in codes}
    by_name: dict[str, list[str]] = defaultdict(list)
    for code, name in NAMES.items():
        by_name[fold(name)].append(code)

    def same(a: str, b: str) -> bool:
        fa, fb = fold(a), fold(b)
        return bool(fa and fb) and (fa == fb or fa in fb or fb in fa)

    outline: dict[str, str] = {}
    for code, row in weredas.items():
        if code in NAMES and same(NAMES[code], row["name"]):
            outline[code] = code
    # The same code under a spelling alike (Kelete Awelallo is Kilte Awulaelo,
    # Mehale Meda town Mehal Meda town), where the region's codes were not
    # reissued.
    for code, row in weredas.items():
        if code not in outline and code in NAMES and code[:4] not in REISSUED \
                and code not in set(outline.values()) \
                and SequenceMatcher(None, fold(NAMES[code]), fold(row["name"])).ratio() >= ALIKE:
            outline[code] = code
    claimed = set(outline.values())
    for code, row in weredas.items():
        if code not in outline:
            hits = [c for c in by_name.get(fold(row["name"]), []) if c not in claimed]
            if len(hits) == 1:
                outline[code] = hits[0]
                claimed.add(hits[0])
    # Then by the name without a special wereda's label or a bracketed
    # region ("Tembaro" is "Tembaro Special", "Awra (TG)" is Tigray's "Awra"),
    # the one such outline in the same region's codes: Tigray's western weredas
    # are coded ET99 in the outlines, and SNNPR's weredas went to four regions.
    by_base: dict[str, list[str]] = defaultdict(list)
    for c, name in NAMES.items():
        by_base[bare(name)].append(c)
    for code, row in weredas.items():
        if code not in outline:
            family = REGION_FAMILY.get(code[:4], {code[:4]})
            hits = [c for c in by_base.get(bare(row["name"]), [])
                    if c not in claimed and c[:4] in family]
            if len(hits) == 1:
                outline[code] = hits[0]
                claimed.add(hits[0])
    unknown_zones = defaultdict(list)
    for code, row in weredas.items():
        if code not in outline:
            unknown_zones[row["zone"]].append(code)
    # A wereda matched to no outline still lies in its zone of 2022. Where every
    # matched wereda of that zone lies in one zone as drawn, and none straddles
    # its line, the zone of 2022 is inside that drawn zone, and so is the wereda.
    drawn_of: dict[str, set[str]] = defaultdict(set)
    for code, row in weredas.items():
        if code in outline:
            drawn_of[row["zone"]].add(home.get(outline[code], "straddling"))
    placed_by_zone: dict[str, list[str]] = defaultdict(list)
    unlocated: set[str] = set()
    for zone, codes in sorted(unknown_zones.items()):
        inside = drawn_of.get(zone, set())
        names = [f"{weredas[c]['name']} ({c}, {weredas[c]['total']:,})" for c in codes]
        if not inside:
            # A zone none of whose weredas matched by name (Mekelle, one wereda in
            # the projection and seven sub-cities in the outlines) is found by its
            # code among the outlines', where the code is the same.
            inside = {home.get(c, "straddling") for c in NAMES if c[:6] == zone}
        if len(inside) == 1 and "straddling" not in inside:
            placed_by_zone[next(iter(inside))] += codes
            report.append(f"projection weredas matched to no outline, in zone {zone}, placed "
                          f"with the zone's other weredas: {names}")
        else:
            if not inside:
                unlocated.add(zone[:4])
            report.append(f"projection weredas matched to no outline, in zone {zone}, whose "
                          f"weredas lie in {sorted(inside)}: {names}")
    labels = {s["id"]: s["name"].strip() for s in admin2}
    region_of = {s["id"]: s["name"].strip() for s in admin1}
    for code, row in weredas.items():
        row["outline"] = outline.get(code)
        row["drawn"] = home.get(outline[code], "straddling") if code in outline else None
    for code in (c for codes in placed_by_zone.values() for c in codes):
        weredas[code]["drawn"] = next(s for s, cs in placed_by_zone.items() if code in cs)

    def inside(code: str, sid: str) -> float:
        """How much of a projection wereda's outline lies more than 2 km inside a
        zone polygon it is not placed in (SHARES)."""
        return SHARES.get(weredas[code].get("outline") or "", {}).get(sid, 0.0)

    def beyond_line(code: str, sid: str) -> float:
        """How much of the outline of a wereda placed in ``sid`` lies more than 2 km
        inside other zone polygons."""
        return sum(v for k, v in SHARES.get(weredas[code].get("outline") or "", {}).items()
                   if k != sid)

    def area(code: str) -> float:
        return areas.get(weredas[code].get("outline") or "", 0.0)

    for sid in sorted(labels, key=lambda s: labels[s]):
        codes = [c for c in weredas if c in outline and home.get(outline[c]) == sid]
        codes += placed_by_zone.get(sid, [])
        zones = {weredas[c]["zone"] for c in codes}
        blind = sorted(z for z in zones if z in unknown_zones
                       and any(c not in codes for c in unknown_zones[z]))
        # A zone of 2022 that could not be found at all may lie in any drawn zone of
        # its region, so none of them is written.
        parent = next((s["parent"] for s in admin2 if s["id"] == sid), None)
        lost = sorted(unlocated & REGION_CODES.get(region_of.get(parent, ""), set()))
        blind += [f"a zone of region {r} not found" for r in lost]
        if not codes or blind or sid not in labels:
            if codes or blind:
                report.append(f"{labels.get(sid, sid)}: not written -- {len(codes)} weredas, "
                              f"zones holding weredas matched to no outline {blind}")
            continue
        total = sum(weredas[c]["total"] for c in codes)
        # The people of the zone's ground in weredas placed elsewhere or nowhere,
        # and the people of its weredas beyond its line, each wereda's people
        # spread evenly over its outline, and only the outline's parts more than
        # 2 km from the line counted (nearer it, two drawings of one line
        # disagree).
        taken_in = sorted(((inside(c, sid) * w["total"], c) for c, w in weredas.items()
                           if c not in codes and inside(c, sid) > 0), reverse=True)
        beyond = sorted(((beyond_line(c, sid) * weredas[c]["total"], c) for c in codes
                         if beyond_line(c, sid) > 0), reverse=True)
        left_out = sum(n for n, _ in taken_in)
        spilled = sum(n for n, _ in beyond)
        # The same in area: the zone's weredas' outlines, the parts of others more
        # than 2 km inside its line, and the parts of its own more than 2 km beyond.
        ground = sum(area(c) for c in codes)
        left_area = sum(inside(c, sid) * area(c) for _, c in taken_in)
        spilled_area = sum(beyond_line(c, sid) * area(c) for _, c in beyond)
        by_people = left_out <= SLIVER * total and spilled <= SLIVER * total
        by_area = ground > 0 and left_area <= SLIVER * ground and spilled_area <= SLIVER * ground
        shares = (f"people {left_out / total:.1%} left out, {spilled / total:.1%} beyond; area "
                  f"{left_area / ground if ground else 1:.1%} left out, "
                  f"{spilled_area / ground if ground else 1:.1%} beyond")
        if not (by_people or by_area):
            report.append(f"{labels[sid]}: not written -- of its sum {total:,}, weredas "
                          f"straddling its line leave out about {left_out:,.0f} "
                          f"({[weredas[c]['name'] for _, c in taken_in[:4]]}) and take in about "
                          f"{spilled:,.0f} from beyond it "
                          f"({[weredas[c]['name'] for _, c in beyond[:4]]}); {shares}")
            continue
        named_in = [weredas[c]["name"] for n, c in taken_in if n > NAMED * total]
        named_out = [weredas[c]["name"] for n, c in beyond if n > NAMED * total]
        note = ("The statistics office's projection for July 2022, from the 2007 census, for "
                "the one wereda that lies within the zone as drawn." if len(codes) == 1 else
                f"The statistics office's projections for July 2022, from the 2007 census, for "
                f"the {len(codes)} weredas that lie within the zone as drawn, added up.")
        if named_in:
            note += (f" The zone as drawn also takes in part of {listed(named_in)} "
                     f"{'wereda' if len(named_in) == 1 else 'weredas'}, whose people are not "
                     "in this figure.")
        if named_out:
            note += (f" Part of {listed(named_out)} "
                     f"{'wereda' if len(named_out) == 1 else 'weredas'}, counted here, lies "
                     "beyond the zone's line.")
        report.append(f"{labels[sid]}: {total:,} from {len(codes)} weredas; about "
                      f"{left_out:,.0f} left out, {spilled:,.0f} taken in from beyond "
                      f"(named: {named_in}, {named_out}); {shares}"
                      f"{'' if by_people else ' (a sliver by area)'}")
        records.append(record(
            f"ETH-2022-{sid}", labels[sid], level="admin2", parent="ETH", country="ETH",
            match_by="shape_id", shape_id=sid,
            population=measure(total, year=PROJECTION_YEAR, source=PROJECTION_SOURCE),
            population_note=note, sources=cite))
    # A region drawn as a single zone takes the region's projection.
    written = {r["shape_id"] for r in records if r["level"] == "admin2"}
    for shape in admin2:
        keys = PROJECTION_WHOLE.get(shape["name"].strip())
        if not keys or shape["id"] in written:
            continue
        total = sum(regions[k]["total"] for k in keys)
        records.append(record(
            f"ETH-2022-{shape['id']}", shape["name"].strip(), level="admin2", parent="ETH",
            country="ETH", match_by="shape_id", shape_id=shape["id"],
            population=measure(total, year=PROJECTION_YEAR, source=PROJECTION_SOURCE),
            population_note=("The statistics office's projection for July 2022, from the 2007 "
                             "census, for the region, which is drawn as this one zone."),
            sources=cite))
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
        return write_cod_points("cod-ab-eth", 3, WEREDA_POINTS, 30)
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
    regions, weredas, page = projection_tables()
    areas = {str(u["props"]["adm3_pcode"]): float(u.get("area_km2") or 0.0)
             for u in json.loads((PROCESSED / WEREDA_POINTS).read_text())}
    projected, report = projection_records(regions, weredas, page, admin1, admin2, areas)
    for line in report:
        log("  " + line)
    for r in projected:
        log(f"  projection {r['level']} {r['name']}: {r['population']['value']:,}")
    log(f"  projection: {sum(1 for r in projected if r['level'] == 'admin1')} regions and "
        f"{sum(1 for r in projected if r['level'] == 'admin2')} zones written")
    write_json(PROCESSED / PROJECTION_OUT, projected)
    write_json(PROCESSED / PROJECTION_WEREDAS,
               [{"code": c, **w} for c, w in sorted(weredas.items())])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
