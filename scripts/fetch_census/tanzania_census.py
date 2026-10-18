#!/usr/bin/env python3
"""Tanzania -- the 2022 census by region and council, on the councils drawn.

The National Bureau of Statistics' "Administrative Units Population
Distribution Report" (2022 Population and Housing Census, Volume 1a) opens each
region's chapter with a table of its councils: population by sex, sex ratio,
households and average household size. A line reads

    Kondoa District Council 244,854 124,379 120,475 103 52,677 4.6

**Checks before anything is written.** Each line's men and women make its
total; each region's councils make the region; the regions make Tanzania,
61,741,120.

**Binding.** The boundary file draws the councils of about 2012 (district
councils, and the towns and municipalities beside them as "X Urban" or "X
Township Authority"). Councils made since are added to the one they were made
from (Ubungo to Kinondoni, Kigamboni to Temeke, Chalinze to Bagamoyo...;
POOLED). A polygon is written only when every council it takes is in the
table, and only when its count moves with the region's: against OCHA's 2020
projection for the same unit, built on the 2012 census, the polygon's 2022
count's ratio to it must be within a factor of 1.4 of its region's own ratio
(``TOLERANCE``), either way. A town that grew past
its old outline fails that test, and so does the district it grew out of:
FAMILIES holds the polygons drawn from one district of 2012, which stand or
fall together. Kahama and Katavi's districts, split three and four ways since
2012 along lines the boundary file does not draw, are left out.

The first level is the 2012 regions too: Songwe, made from Mbeya in 2016, is
drawn inside it, and Mbeya's polygon takes both regions' counts and says so.

Songwe District Council, made from the western part of Chunya in 2015-16, is
drawn apart from it on the lines of the split -- each polygon's area is the
district's published one (AREA_CHECKED) -- while OCHA's table projects the two
as the one district of 2012; each takes its own council's count, without the
ratio test.

**Median age.** The census's Age and Sex Distribution Report (Volume 2a)
prints everyone by single year of age, to 79 and 80 and over, for every region
and council. Each table's single years and sexes must make its total, and the
total must be Volume 1a's count of the same unit; a polygon's median is
interpolated within the single year that holds its middle person, from the
tables of the councils (or regions) it adds up.

Usage:
    python -m scripts.fetch_census.tanzania_census
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
from collections import defaultdict
from typing import Any

from ._shared import PROCESSED, http_get, log, measure, record, write_json
from .cod_ps_age import grouped_median

URL = ("https://www.nbs.go.tz/uploads/statistics/documents/"
       "en-1705484562-Administrative_units_Population_Distribution_Report_Tanzania_volume1a.pdf")
SOURCE = ("National Bureau of Statistics (Tanzania), 2022 Population and Housing Census, "
          "Administrative Units Population Distribution Report, Volume 1a")
LICENCE = "NBS Tanzania publication (reuse with attribution)"
YEAR = 2022
NATIONAL = 61_741_120
OUT = "tanzania_census.json"
SITE = PROCESSED.parent.parent / "site" / "data"
# How far a polygon's 2022/2020 ratio may stray from its region's before the
# polygon is taken to be drawn differently from the council counted.
TOLERANCE = 1.4

# A table row: "Kondoa District Council 244,854 124,379 120,475 103 52,677 4.6",
# numbered ("5. Mbinga District 285,582 ...") in a region's table of councils,
# and now and then printed without thousands separators.
LINE = re.compile(r"^(?:(?P<num>\d+)\.\s*)?(?P<name>[A-Za-z][A-Za-z' .-]*?)\s+"
                  r"(?P<total>\d[\d,]*)\s+(?P<men>\d[\d,]*)\s+(?P<women>\d[\d,]*)\s+"
                  r"(?P<ratio>\d+(?:\.\d+)?)\s+(?P<hh>\d[\d,]*(?:\.\d+)?)\s+"
                  r"(?P<avg>\d+(?:\.\d+)?)$")
COUNCIL = re.compile(r"(?i)\b(?:district|distict|town|municipal|city)(?:\s+council)?$")
KINDS = ("district", "town", "municipal", "city")

# The census's region -> the first-level polygon it is drawn in.
REGIONS = {"kaskaziniunguja": "Zanzibar North", "kusiniunguja": "Zanzibar South & Central",
           "mjinimagharibi": "Zanzibar Urban/West", "kaskazinipemba": "North Pemba",
           "kusinipemba": "South Pemba", "songwe": "Mbeya"}
# Councils made since 2012, by the drawn polygon whose councils they were.
POOLED = {
    "Kinondoni": ["kinondoni municipal", "ubungo municipal"],
    "Temeke": ["temeke municipal", "kigamboni municipal"],
    "Ilala": ["dar es salaam city"],
    "Kondoa": ["kondoa district", "kondoa town"],
    "Geita": ["geita district", "geita town"],
    "Lushoto": ["lushoto district", "bumbuli district"],
    "Bagamoyo": ["bagamoyo district", "chalinze district"],
    "Rufiji": ["rufiji district", "kibiti district"],
    "Kilombero": ["mlimba district", "ifakara town"],
    "Ulanga": ["ulanga district", "malinyi district"],
    "Mtwara": ["mtwara district", "nanyamba town"],
    "Newala": ["newala district", "newala town"],
    "Songea": ["songea district", "madaba district"],
    "Mbinga": ["mbinga district", "mbinga town"],
    "Manyoni": ["manyoni district", "itigi district"],
    "Nzega": ["nzega district", "nzega town"],
    "Sengerema": ["sengerema district", "buchosa district"],
    "Tarime": ["tarime district", "tarime town"],
    "Bunda": ["bunda district", "bunda town"],
    "Mbulu": ["mbulu district", "mbulu town"],
    "Bariadi": ["bariadi district", "bariadi town"],
    "Rungwe": ["rungwe district", "busokelo district"],
    "Magharibi": ["magharibi a municipal", "magharibi b municipal"],
    "Nyamagana": ["mwanza city"],
    "Tanga Urban": ["tanga city"],
    "Handeni Mji": ["handeni town"],
    "Butiam": ["butiama district"],
    "Kaskazini B": ["kaskazini b town"],
    "Kati": ["kati town"],
    "Tunduma": ["tunduma town"],
}
# Polygons not written, and why (logged).
LEFT_OUT = {
    "Kahama": "Kahama's councils were redrawn as Kahama, Ushetu and Msalala in 2012-2018",
    "Kahama Township Authority": "see Kahama",
    "Mpanda": "Katavi's districts were split into Mpanda, Nsimbo, Tanganyika and Mpimbwe",
    "Mpanda Urban": "see Mpanda", "Mlele": "see Mpanda",
}
# Polygons whose outline is shown to be the council's by its area, so the
# ratio test against OCHA's 2020 table does not apply to them. Songwe District
# Council was made from the western part of Chunya in 2015-16; the boundary
# file draws the two as they are since (Chunya 17,502 km2 against the
# district's published 17,505; Songwe 16,198 against 16,070), and OCHA's
# "Chunya" is the district before the split, with no row for Songwe.
AREA_CHECKED = {"Chunya": 17_505, "Songwe": 16_070}
# OCHA's units for polygons no rule names.
COD_NAMES = {"Tanga Urban": "TANGA", "Mtwara Urban": "MTWARA MIKINDANI",
             "Kigoma Urban": "KIGOMA UJIJI MUNICIPAL", "Mafinga Township Authority": "MAFINGA",
             "Butiam": "BUTIAMA", "Babati Urban": "BABATI TOWN", "Handeni Mji": "HANDENI TOWN"}
# Polygons drawn from one district of 2012: they stand or fall together.
FAMILIES = [
    {"Korogwe", "Korogwe Township Authority"}, {"Handeni", "Handeni Mji"},
    {"Masasi", "Masasi Township Authority"}, {"Mufindi", "Mafinga Township Authority"},
    {"Kasulu", "Kasulu Township Authority"}, {"Kibaha", "Kibaha Urban"},
    {"Babati", "Babati Urban"}, {"Njombe", "Njombe Urban", "Makambako Township Authority"},
    {"Momba", "Tunduma", "Mbozi"}, {"Mbeya", "Mbeya Urban"},
    {"Iringa", "Iringa Urban"}, {"Moshi", "Moshi Urban"}, {"Arusha", "Arusha Urban"},
    {"Morogoro", "Morogoro Urban"}, {"Lindi", "Lindi Urban"}, {"Mtwara", "Mtwara Urban"},
    {"Songea", "Songea Urban"}, {"Singida", "Singida Urban"}, {"Sumbawanga", "Sumbawanga Urban"},
    {"Kigoma", "Kigoma Urban", "Uvinza"}, {"Shinyanga", "Shinyanga Urban"},
    {"Bukoba", "Bukoba Urban", "Missenyi"}, {"Musoma", "Musoma Urban", "Butiam"},
    # Districts made around 2012 from another.
    {"Iramba", "Mkalama"}, {"Kasulu", "Kasulu Township Authority", "Buhigwe"},
    {"Kibondo", "Kakonko"}, {"Karagwe", "Kyerwa"}, {"Sumbawanga", "Sumbawanga Urban", "Kalambo"},
    {"Bukombe", "Mbogwe"}, {"Singida", "Singida Urban", "Ikungi"}, {"Bariadi", "Itilima"},
    {"Magu", "Busega"}, {"Kilosa", "Gairo"}, {"Muheza", "Mkinga"}, {"Mbinga", "Nyasa"},
    {"Urambo", "Kaliua"}, {"Njombe", "Wanging'ombe"}, {"Kaskazini A", "Kaskazini B"},
]


def label(name: str) -> str:
    """A polygon label tidied: single spaces, a doubled 'Babati Urban' once."""
    text = " ".join(str(name or "").split())
    half = len(text) // 2
    if len(text) % 2 == 0 and text[:half] == text[half:]:
        text = text[:half]
    return text


def council_key(name: str) -> str:
    # One report prints Nyang'hwale with a straight apostrophe, another with a
    # curly one.
    text = " ".join(name.lower().replace("distict", "district").replace("’", "'").split())
    return re.sub(r"\s+council$", "", text)


def region_key(name: str) -> str:
    return re.sub(r"[^a-z]", "", re.sub(r"(?i)\s+region$", "", name).lower())


def number(text: str) -> int:
    return int(text.replace(",", "").split(".")[0])


def parse(lines: list[str], strict: bool = True) -> dict[str, Any]:
    """{"regions": {key: row}, "councils": {key: row}}; a council row carries
    its region's key."""
    out: dict[str, Any] = {"national": None, "regions": {}, "councils": {}}
    region = None
    table = None                                    # "council" or "ward": the table being read
    for raw in lines:
        lowered = raw.lower()
        if "by council" in lowered:
            table = "council"
        elif "by ward" in lowered:
            table = "ward"
        hit = LINE.match(raw.strip())
        if not hit:
            continue
        name = hit.group("name").strip()
        # A ward table's rows are wards, but for its first: the council's own total.
        if not name.lower().endswith(" region") and (
                not COUNCIL.search(name) or (table == "ward" and hit.group("num"))):
            continue
        total, men, women = (number(hit.group(k)) for k in ("total", "men", "women"))
        if men + women != total:
            raise SystemExit(f"tanzania_census: {name}: {men:,} men and {women:,} women do not "
                             f"make {total:,}")
        row = {"name": name, "total": total, "men": men, "women": women}
        lower = name.lower()
        if lower in ("tanzania", "tanzania mainland", "tanzania zanzibar"):
            if lower == "tanzania":
                out["national"] = total
            continue
        if lower.endswith(" region"):
            region = region_key(name)
            if out["regions"].get(region, row) != row:
                raise SystemExit(f"tanzania_census: {name} is printed two ways")
            out["regions"][region] = row
            continue
        if COUNCIL.search(name):
            name = re.sub(r"(?i)\s+council$", "", name).replace("Distict", "District") + " Council"
            row["name"] = name
            if region is None:
                raise SystemExit(f"tanzania_census: {name} comes before any region")
            key = council_key(name)
            row["region"] = region
            seen = out["councils"].get(key)
            if seen is not None:
                if [seen[f] for f in ("total", "men", "women", "region")] != \
                        [row[f] for f in ("total", "men", "women", "region")]:
                    raise SystemExit(f"tanzania_census: {name} is printed two ways")
                continue
            out["councils"][key] = row
    out["unread"] = check(out) if strict else {}
    return out


def check(table: dict[str, Any]) -> dict[str, str]:
    """The regions whose councils were not all read, and why. The regions
    themselves must make the country."""
    made = sum(r["total"] for r in table["regions"].values())
    if made != NATIONAL:
        raise SystemExit(f"tanzania_census: the {len(table['regions'])} regions make {made:,}, "
                         f"not {NATIONAL:,}")
    unread = {}
    for key, region in table["regions"].items():
        rows = [c for c in table["councils"].values() if c["region"] == key]
        if sum(c["total"] for c in rows) != region["total"]:
            unread[key] = (f"{region['name']}'s {len(rows)} councils read make "
                           f"{sum(c['total'] for c in rows):,}, not {region['total']:,}: "
                           f"{sorted(c['name'] for c in rows)}")
    return unread


def councils_for(name: str, available: set[str]) -> list[str] | None:
    """The councils a drawn polygon takes, or None."""
    if name in POOLED:
        return POOLED[name]
    base, _, kind = name.rpartition(" ")
    if name.endswith(" Township Authority"):
        candidates = [name[:-len(" Township Authority")].lower() + " town"]
    elif kind == "Urban":
        candidates = [f"{base.lower()} {k}" for k in ("municipal", "city", "town")]
    else:
        candidates = [f"{name.lower()} {k}" for k in KINDS]
    present = [c for c in candidates if c in available]
    if name.endswith(" Township Authority") or kind == "Urban":
        return present if len(present) == 1 else None
    district = f"{name.lower()} district"
    if district in available:
        return [district]
    return present if len(present) == 1 else None


def cod_for(name: str, cod: dict[str, int]) -> int | None:
    if name in COD_NAMES:
        return cod.get(COD_NAMES[name])
    upper = name.upper()
    if name.endswith(" Township Authority"):
        return cod.get(upper[:-len(" TOWNSHIP AUTHORITY")] + " TOWN")
    if name.endswith(" Urban"):
        base = upper[:-len(" URBAN")]
        hits = [cod[k] for k in (base + " MUNICIPAL", base + " CITY", base + " TOWN") if k in cod]
        return hits[0] if len(hits) == 1 else None
    return cod.get(upper)


def fields(row: dict[str, Any], note: str, ages: list[dict[str, Any]] | None = None
           ) -> dict[str, Any]:
    """The record's figures; ``ages`` are the age tables of the units it adds up, if read."""
    out = {"population": measure(row["total"], year=YEAR, source=SOURCE),
           "population_note": note,
           "sex_ratio": measure(round(1000 * row["men"] / row["women"]),
                                unit="males_per_1000_females", year=YEAR, source=SOURCE),
           "sources": [{"field": "population/sex_ratio", "name": SOURCE, "url": URL,
                        "license": LICENCE, "year": YEAR}]}
    if ages:
        value = age_median(ages)
        if value is not None:
            out["median_age"] = measure(value, unit="years", year=YEAR, source=AGE_SOURCE)
            out["median_age_note"] = (
                "Interpolated within the single year of age that holds the middle person, from "
                "the 2022 census's count of everyone by single year of age"
                + (f", of {' and '.join(a['name'] for a in ages)} together." if len(ages) > 1
                   else f", its {len(ages[0]['parts'])} councils' counts added up."
                   if ages[0].get("parts") else "."))
            out["sources"].append({"field": "median_age", "name": AGE_SOURCE, "url": AGE_URL,
                                   "license": LICENCE, "year": YEAR})
    return out


# The Age and Sex Distribution Report (Volume 2a) prints, for the country, every
# region and every council, everyone by single year of age to 79 and 80 and
# over, by sex and by rural and urban residence. A table opens
#
#   Table 02. 1: Monduli District Council: Population Distribution by Age, Sex ...
#
# and runs over two pages, its header repeated; a row reads "17 3,947 1,789
# 2,158 ..." (both sexes, men, women, then rural and urban).
AGE_URL = ("https://www.nbs.go.tz/uploads/statistics/documents/"
           "en-1705484562-Age_and_Sex_Distribution_Report_Tanzania_volume2a.pdf")
AGE_SOURCE = ("National Bureau of Statistics (Tanzania), 2022 Population and Housing Census, "
              "Age and Sex Distribution Report, Volume 2a")
AGE_TABLE = re.compile(r"^Table\s+\d+\s*\.\s*\d+\s*:\s*(?P<name>.+?)\s*:\s*Population Distribution "
                       r"by Age", re.I)
AGE_ROW = re.compile(r"^(?P<age>\d{1,2}|80\s*\+|Total)\s+(?P<both>\d[\d,]*)\s+(?P<men>\d[\d,]*)\s+"
                     r"(?P<women>\d[\d,]*)(?:\s|$)")


def parse_ages(lines: list[str]) -> dict[str, dict[str, Any]]:
    """{"regions": {key: table}, "councils": {key: table}}, each table checked: its single
    years make its total, and its men and women make it too."""
    out: dict[str, Any] = {"regions": {}, "councils": {}, "unread": []}
    current: dict[str, Any] | None = None

    def close(table: dict[str, Any] | None) -> None:
        if table is None:
            return
        name = table["name"]
        # A table whose page the text layer does not give whole is left out
        # and named: its unit keeps no census median, never a partial one.
        if table["total"] is None or len(table["ages"]) != 81:
            out["unread"].append(f"{name}: {len(table['ages'])} single years read, total "
                                 f"{table['total']}")
            return
        made = sum(table["ages"].values())
        if made != table["total"] or table["men"] + table["women"] != table["total"]:
            out["unread"].append(f"{name}: single years make {made:,} and sexes "
                                 f"{table['men'] + table['women']:,}, against "
                                 f"{table['total']:,}")
            return
        lower = name.lower()
        if lower.startswith("tanzania"):
            return
        if lower.endswith(" region"):
            out["regions"][region_key(name)] = table
        elif COUNCIL.search(re.sub(r"(?i)\s+council$", "", name)) or lower.endswith(" council"):
            out["councils"][council_key(name)] = table
        else:
            raise SystemExit(f"tanzania_census: an age table of {name!r}, neither region nor "
                             "council")

    for raw in lines:
        line = " ".join(raw.split())
        head = AGE_TABLE.match(line)
        if head:
            name = head.group("name").replace("Distict", "District")
            if current is None or current["name"] != name:
                close(current)
                current = {"name": name, "total": None, "men": 0, "women": 0, "ages": {}}
            continue
        hit = AGE_ROW.match(line)
        if not hit or current is None:
            continue
        both, men, women = (number(hit.group(k)) for k in ("both", "men", "women"))
        if men + women != both:
            # A row the text layer garbled: the table fails its total below.
            current.setdefault("garbled", []).append(hit.group("age"))
            continue
        age = hit.group("age").replace(" ", "")
        if age == "Total":
            current.update(total=both, men=men, women=women)
        else:
            key = 80 if age == "80+" else int(age)
            if key in current["ages"] and current["ages"][key] != both:
                raise SystemExit(f"tanzania_census: {current['name']}, age {age} printed twice")
            current["ages"][key] = both
    close(current)
    return out


def age_median(tables: list[dict[str, Any]]) -> float | None:
    """The median of several age tables added together, single year by single year."""
    groups = [(a, a, sum(t["ages"][a] for t in tables)) for a in range(80)]
    groups.append((80, None, sum(t["ages"][80] for t in tables)))
    return grouped_median(groups)


# Councils Volume 2a names otherwise than Volume 1a (a council's type, a
# spelling, Lindi District Council's new name): {2a key: 1a key}. A table taken
# this way must still count Volume 1a's people, men and women exactly.
AGE_ALIASES = {
    "busekelo district": "busokelo district",
    "chake chake district": "chake chake town",
    "kaskazini a town": "kaskazini a district",
    "kaskazini b district": "kaskazini b town",
    "kati district": "kati town",
    "misenyi district": "missenyi district",
    "mtama district": "lindi district",
    "mtwara mikindani municipal": "mtwara municipal",
    "wanging'ombe town": "wanging'ombe district",
    "wete district": "wete town",
}


def check_ages(ages: dict[str, dict[str, Any]], table: dict[str, Any]) -> list[str]:
    """Each age table's total must be the Volume 1a count of the same unit. A region
    whose own table is not read takes its councils' tables added up, when every one
    of them is read and they make the region."""
    report = []
    for old, new in AGE_ALIASES.items():
        if old in ages["councils"] and new not in ages["councils"]:
            ages["councils"][new] = ages["councils"].pop(old)
    for kind in ("regions", "councils"):
        spare = sorted(t["name"] for k, t in ages[kind].items() if k not in table[kind])
        if spare:
            report.append(f"age tables matching no Volume 1a {kind[:-1]}: {spare}")
        for key, row in table[kind].items():
            got = ages[kind].get(key)
            if got is None:
                report.append(f"no age table for {row['name']}")
            elif (got["total"], got["men"], got["women"]) != (row["total"], row["men"],
                                                              row["women"]):
                # Not the same people, or not read the same way: no median for it.
                report.append(f"{row['name']}: the age table counts {got['total']:,} "
                              f"({got['men']:,} men), Volume 1a {row['total']:,} "
                              f"({row['men']:,} men); its age table is left out")
                ages[kind].pop(key)
            else:
                # The same unit: named as Volume 1a names it, which the population
                # note beside the median does ("Busokelo", where Volume 2a's
                # table heading spells it "Busekelo").
                got["name"] = row["name"]
    for key, row in table["regions"].items():
        if key in ages["regions"]:
            continue
        parts = [ages["councils"].get(k) for k, c in table["councils"].items()
                 if c["region"] == key]
        if not parts or not all(parts):
            continue
        summed = {"name": row["name"], "parts": [p["name"] for p in parts],
                  "ages": {a: sum(p["ages"][a] for p in parts) for a in parts[0]["ages"]},
                  **{f: sum(p[f] for p in parts) for f in ("total", "men", "women")}}
        if (summed["total"], summed["men"], summed["women"]) == (row["total"], row["men"],
                                                                  row["women"]):
            ages["regions"][key] = summed
            report.append(f"{row['name']}: ages from its {len(parts)} councils' tables added up")
    return report


def build(table: dict[str, Any], admin1: list[dict[str, Any]], admin2: list[dict[str, Any]],
          cod: dict[str, int], ages: dict[str, dict[str, Any]] | None = None
          ) -> tuple[list[dict[str, Any]], list[str]]:
    records: list[dict[str, Any]] = []
    report: list[str] = []
    ages = ages or {"regions": {}, "councils": {}}

    def aged(kind: str, keys: list[str]) -> list[dict[str, Any]] | None:
        found = [ages[kind].get(k) for k in keys]
        return found if found and all(found) else None
    first = {label(u["name"]): u for u in admin1}
    by_polygon: dict[str, list[str]] = defaultdict(list)
    for key, row in table["regions"].items():
        polygon = REGIONS.get(key) or row["name"][:-len(" Region")]
        by_polygon[polygon].append(key)
    region_of_shape: dict[str, list[str]] = {}
    for polygon, keys in by_polygon.items():
        shape = first.get(polygon)
        if shape is None:
            report.append(f"no first-level polygon {polygon!r} for {keys}")
            continue
        region_of_shape[shape["id"]] = keys
        rows = [table["regions"][k] for k in keys]
        row = {f: sum(r[f] for r in rows) for f in ("total", "men", "women")}
        if len(rows) == 1:
            note = f"The 2022 census's count for {rows[0]['name']}."
        else:
            note = ("The 2022 census's counts for " + " and ".join(r["name"] for r in rows)
                    + ", added up: Songwe Region was made from Mbeya in 2016 and is drawn "
                      "inside it.")
        records.append(record(f"TZA-2022-{'-'.join(keys)}", shape["name"], level="admin1",
                              parent="TZA", country="TZA", match_by="shape_id",
                              shape_id=shape["id"], **fields(row, note, aged("regions", keys))))
    # Second level, region by region.
    plans: dict[str, dict[str, Any]] = {}
    unread = table.get("unread") or {}
    for key, why in unread.items():
        report.append(f"{key}: second level left out -- {why}")
    for shape in admin2:
        name = label(shape["name"])
        keys = region_of_shape.get(shape["parent"], [])
        if any(k in unread for k in keys):
            continue
        available = {k for k, c in table["councils"].items() if c["region"] in keys}
        if name in LEFT_OUT:
            report.append(f"{name}: left out -- {LEFT_OUT[name]}")
            continue
        took = councils_for(name, available)
        if not took or any(c not in available for c in took):
            report.append(f"{name}: no council of that name in its region ({took})")
            continue
        rows = [table["councils"][c] for c in took]
        plans[name] = {"shape": shape, "councils": took, "regions": keys,
                       "row": {f: sum(r[f] for r in rows) for f in ("total", "men", "women")},
                       "cod": cod_for(name, cod)}
    used: dict[str, str] = {}
    for name, plan in plans.items():
        for c in plan["councils"]:
            if c in used:
                report.append(f"{c} taken by both {used[c]} and {name}")
            used[c] = name
    # A polygon shown to be its council by area takes no part in the ratio test.
    for name in AREA_CHECKED:
        if name in plans:
            plans[name]["cod"] = None
            report.append(f"{name}: outline checked by area ({AREA_CHECKED[name]:,} km2); "
                          "no ratio test")
    # Each region's ratio of 2022 counts to OCHA's 2020 projection.
    ratio: dict[str, float] = {}
    for keys in region_of_shape.values():
        mine = [p for p in plans.values() if p["regions"] == keys and p["cod"]]
        if mine:
            ratio[keys[0]] = (sum(p["row"]["total"] for p in mine)
                              / sum(p["cod"] for p in mine))
    failed = set()
    for name, plan in plans.items():
        expected = ratio.get(plan["regions"][0])
        if plan["cod"] and expected:
            own = plan["row"]["total"] / plan["cod"]
            plan["ratio"] = own / expected
            if not 1 / TOLERANCE <= own / expected <= TOLERANCE:
                failed.add(name)
    report.append("against the region's ratio: " + ", ".join(
        f"{n} {p['ratio']:.2f}" for n, p in sorted(plans.items(), key=lambda x: x[1].get("ratio", 1))
        if "ratio" in p))
    for family in FAMILIES:
        # Siblings drawn from one district that moved apart -- one well above its
        # region, one well below -- are drawn on a line the census does not use.
        ratios = [plans[n]["ratio"] for n in family if n in plans and "ratio" in plans[n]]
        if len(ratios) > 1 and max(ratios) / min(ratios) > TOLERANCE:
            report.append(f"{sorted(family & set(plans))}: drawn from one district, at "
                          f"{min(ratios):.2f} and {max(ratios):.2f} of their region's ratio; "
                          "not written")
            failed |= family & set(plans)
    grown = True
    while grown:                                    # families overlap: to a fixed point
        grown = False
        for family in FAMILIES:
            if family & failed and (family & set(plans)) - failed:
                for name in (family & set(plans)) - failed:
                    report.append(f"{name}: left out with {sorted(family & failed)}, drawn from "
                                  "the same district of 2012")
                failed |= family & set(plans)
                grown = True
    for name in sorted(plans):
        plan = plans[name]
        shape = plan["shape"]
        rows = [table["councils"][c] for c in plan["councils"]]
        if name in failed:
            report.append(f"{name}: {plan['row']['total']:,} against OCHA's {plan['cod']}, "
                          f"{plan.get('ratio', 0):.2f} of its region's ratio; not written")
            continue
        names = [r["name"] for r in rows]
        if len(rows) == 1:
            note = f"The 2022 census's count for {names[0]}."
        else:
            note = ("The 2022 census's counts for " + ", ".join(names[:-1]) + " and " + names[-1]
                    + ", added up: the councils made since 2012 from the one drawn here.")
        records.append(record(f"TZA-2022-{shape['id']}", shape["name"], level="admin2",
                              parent="TZA", country="TZA", match_by="shape_id",
                              shape_id=shape["id"],
                              **fields(plan["row"], note, aged("councils", plan["councils"]))))
    spare = sorted(c["name"] for k, c in table["councils"].items() if k not in used)
    report.append(f"councils not placed: {spare}")
    return records, report


def read(blob: bytes) -> dict[str, Any]:
    import pdfplumber                               # noqa: PLC0415
    lines: list[str] = []
    with pdfplumber.open(io.BytesIO(blob)) as pdf:
        for page in pdf.pages[40:]:
            lines += (page.extract_text() or "").splitlines()
    return parse(lines)


def cod_rows() -> dict[str, int]:
    out = {}
    for row in json.loads((PROCESSED / "cod_ps_admin2.json").read_text()):
        if str(row.get("id", "")).startswith("TZA-CODPS-"):
            value = (row.get("population") or {}).get("value")
            if value:
                out[str(row["name"]).upper()] = value
    return out


def read_ages(blob: bytes) -> dict[str, dict[str, Any]]:
    import pdfplumber                               # noqa: PLC0415
    lines: list[str] = []
    with pdfplumber.open(io.BytesIO(blob)) as pdf:
        # Section Four, the tables, begins after the report's own analysis;
        # Dodoma's tables come first and begin before page 80.
        for page in pdf.pages[55:]:
            lines += (page.extract_text() or "").splitlines()
    return parse_ages(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", default="", help="a label that tells two dispatches apart; ignored")
    ap.parse_args()
    blob = http_get(URL, binary=True, cache=False, timeout=300)
    if not blob.startswith(b"%PDF"):
        raise SystemExit(f"tanzania_census: {URL} is not a PDF: {blob[:80]!r}")
    # Which bytes were read, for anyone checking the rows against the file.
    log(f"  read {URL}: {len(blob):,} bytes, sha256 {hashlib.sha256(blob).hexdigest()}")
    table = read(blob)
    log(f"  {len(table['regions'])} regions and {len(table['councils'])} councils, making "
        f"{NATIONAL:,}")
    age_blob = http_get(AGE_URL, binary=True, cache=False, timeout=600)
    if not age_blob.startswith(b"%PDF"):
        raise SystemExit(f"tanzania_census: {AGE_URL} is not a PDF: {age_blob[:80]!r}")
    log(f"  read {AGE_URL}: {len(age_blob):,} bytes, sha256 "
        f"{hashlib.sha256(age_blob).hexdigest()}")
    ages = read_ages(age_blob)
    log(f"  age tables: {len(ages['regions'])} regions and {len(ages['councils'])} councils, "
        "each one's single years and sexes making its total")
    for line in ages["unread"]:
        log(f"  age table left out: {line}")
    for line in check_ages(ages, table):
        log("  " + line)
    admin1 = json.loads((SITE / "admin1" / "TZA.units.json").read_text())
    admin2 = json.loads((SITE / "admin2" / "TZA.units.json").read_text())
    records, report = build(table, admin1, admin2, cod_rows(), ages)
    for line in report:
        log("  " + line)
    for r in records:
        if r["name"] in ("Kinondoni", "Temeke", "Ilala", "Dar es Salaam"):
            log(f"  {r['name']}: {r['population']['value']:,}")
    log(f"  {sum(1 for r in records if r['level'] == 'admin1')} of {len(admin1)} regions and "
        f"{sum(1 for r in records if r['level'] == 'admin2')} of {len(admin2)} districts written")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
