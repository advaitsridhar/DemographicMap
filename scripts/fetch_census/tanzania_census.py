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
count must be within a fifth of its region's own ratio. A town that grew past
its old outline fails that test, and so does the district it grew out of:
FAMILIES holds the polygons drawn from one district of 2012, which stand or
fall together. Kahama and Katavi's districts, split three and four ways since
2012 along lines the boundary file does not draw, are left out.

The first level is the 2012 regions too: Songwe, made from Mbeya in 2016, is
drawn inside it, and Mbeya's polygon takes both regions' counts and says so.

Usage:
    python -m scripts.fetch_census.tanzania_census
"""

from __future__ import annotations

import argparse
import io
import json
import re
from collections import defaultdict
from typing import Any

from ._shared import PROCESSED, http_get, log, measure, record, write_json

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
    "Chunya": "Songwe district was made from Chunya in 2016 and is drawn on its own",
    "Songwe": "see Chunya",
}
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
    text = " ".join(name.lower().replace("distict", "district").split())
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


def fields(row: dict[str, Any], note: str) -> dict[str, Any]:
    return {"population": measure(row["total"], year=YEAR, source=SOURCE),
            "population_note": note,
            "sex_ratio": measure(round(1000 * row["men"] / row["women"]),
                                 unit="males_per_1000_females", year=YEAR, source=SOURCE),
            "sources": [{"field": "population/sex_ratio", "name": SOURCE, "url": URL,
                         "license": LICENCE, "year": YEAR}]}


def build(table: dict[str, Any], admin1: list[dict[str, Any]], admin2: list[dict[str, Any]],
          cod: dict[str, int]) -> tuple[list[dict[str, Any]], list[str]]:
    records: list[dict[str, Any]] = []
    report: list[str] = []
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
                              shape_id=shape["id"], **fields(row, note)))
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
                              shape_id=shape["id"], **fields(plan["row"], note)))
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


def main() -> int:
    argparse.ArgumentParser(description=__doc__,
                            formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    blob = http_get(URL, binary=True, cache=False, timeout=300)
    if not blob.startswith(b"%PDF"):
        raise SystemExit(f"tanzania_census: {URL} is not a PDF: {blob[:80]!r}")
    table = read(blob)
    log(f"  {len(table['regions'])} regions and {len(table['councils'])} councils, making "
        f"{NATIONAL:,}")
    admin1 = json.loads((SITE / "admin1" / "TZA.units.json").read_text())
    admin2 = json.loads((SITE / "admin2" / "TZA.units.json").read_text())
    records, report = build(table, admin1, admin2, cod_rows())
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
