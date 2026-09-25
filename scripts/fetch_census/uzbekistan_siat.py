"""Uzbekistan's districts: permanent population from the Statistics Agency's SIAT.

The agency's open-data portal (siat.stat.uz) publishes indicator 2.01.02.0001,
the permanent population at the start of each year from 2010, for every
region, city and district, keyed by SOATO code, under CC BY 4.0. OCHA's
population table for Uzbekistan names the districts and carries no figure,
and Wikidata has none for most of them, so 163 of the map's 198 were blank.

**Names.** The agency writes "Balykchi district" and "Jalаquduk district" (with
a Cyrillic а); the boundary file writes "Balikchi" and "Djalalkuduk". Each unit
is matched to a shape inside its own region on a key that folds the
romanisations together (kh/x/h, dzh/dj/j, q/k, doubled letters, vowels), and
only where exactly one shape answers; a handful the key cannot reach --
renamings, mostly -- are declared.

**Units the boundary file does not draw.** Uzbekistan has made new districts
and cities since the boundary file was drawn, and the ground of each is still
inside an older shape: Kukdala was carved out of Chirakchi in 2023, so the
agency's 2026 figure for Chirakchi is short by Kukdala's 200,000 people. The
agency's own series says where each came from -- the year a unit first
appears, the unit it came out of loses about that many people -- and that is
read rather than assumed:

  * one district lost at least 60% of the new unit's first figure and no
    other lost 5%: the old shape is the two together, and says so;
  * several did: none of them is the shape the boundary file draws, and each
    is left a gap that says why;
  * a unit in the series from its start and not drawn (Shirin, a city of
    regional rank) is placed by declaration, measured against the shapes.

Usage:
    python -m scripts.fetch_census.uzbekistan_siat --dump   # save the JSON
    python -m scripts.fetch_census.uzbekistan_siat
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any

from ._shared import PROCESSED, log, read_json, record, write_json

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import NOT_AVAILABLE, gap, measure, slugify  # noqa: E402
from common import shard_name  # noqa: E402

INDICATOR = 246
CODE = "2.01.02.0001"
POINTER = f"https://api.siat.stat.uz/sdmx/{INDICATOR}/table/download/?download_format=json"
PAGE = f"https://siat.stat.uz/data/{INDICATOR}/?lang=en"
ROOT = Path(__file__).resolve().parent.parent.parent
DUMP = ROOT / "data" / "raw" / "uzbekistan" / f"siat_{INDICATOR}.json"
SITE = ROOT / "site" / "data"
OUT = PROCESSED / "uzbekistan_siat.json"
LICENCE = "CC BY 4.0"
HEADERS = {"User-Agent": "DemographicMap/1.0 (+https://github.com/advaitsridhar/DemographicMap)",
           "Accept": "application/json"}
TIMEOUT = 120

# The agency's region names to the map's first level.
REGION = {
    "Andijan region": "Andijan Region", "Bukhara region": "Bukhara Region",
    "Fergana region": "Fergana Region", "Jizzakh region": "Jizzakh Region",
    "Namangan region": "Namangan Region", "Navoi region": "Navoiy Region",
    "Kashkadarya region": "Qashqadaryo Region",
    "Republic of Karakalpakstan": "Republic of Karakalpakstan",
    "Samarkand region": "Samarqand Region", "Syrdarya region": "Sirdaryo Region",
    "Surkhandarya region": "Surxondaryo Region", "Tashkent city": "Tashkent",
    "Tashkent region": "Tashkent Region", "Khorezm region": "Xorazm Region",
}
# The boundary file puts three of Tashkent city's districts in Tashkent
# Region; a city district is looked for there as well.
ALSO_IN = {"Tashkent": ("Tashkent Region",)}
# Where the folded key cannot reach: Bo'z district was renamed Bo'ston, and
# the boundary file spells four others its own way.
DECLARED = {
    "Bustan district": "Boz", "Jalаquduk district": "Djalalkuduk",
    "Qorovulbozor district": "Karaulbazar", "Jizzakh city": "Dzhizak city",
    "Piskent district": "Pskent", "Gurlan district": "Gurlen",
}
# Units in the series from its start that the boundary file does not draw,
# with the shapes whose ground may hold them. Shirin's coordinates (40.227 N,
# 69.134 E) fall inside the shape called Bekabad and 0.01 degrees from Khavas,
# on the border of two regions: which holds it cannot be told.
UNDRAWN = {"Shirin city": ("Khavas", "Bekabad")}
# How much of a new unit's first figure one district must have lost to be
# its only source, and how much any other may have lost for that to hold.
SOLE_SOURCE = 0.6
ALSO_SOURCE = 0.05

HOMOGLYPHS = str.maketrans("аеорсухкмтвАЕОРСУХКМТВ", "aeopcyxkmtbAEOPCYXKMTB")
FOLDS = (("dzh", "j"), ("dj", "j"), ("zh", "j"), ("kh", "h"), ("x", "h"), ("q", "k"),
         ("sh", "s"), ("ch", "c"), ("yo", "o"), ("yu", "u"), ("ya", "a"), ("y", "i"),
         ("w", "v"))


def key(name: str) -> str:
    """A name with its romanisation folded away, for matching inside one region."""
    text = unicodedata.normalize("NFKD", name.translate(HOMOGLYPHS))
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    text = re.sub(r"\b(district|city|region|tumani|shahri|shahar)\b|city$", " ", text)
    text = re.sub(r"[‘’'`ʻʼ]", "", text)
    for a, b in FOLDS:
        text = text.replace(a, b)
    text = re.sub(r"[^a-z]", "", text)
    text = re.sub(r"(.)\1+", r"\1", text)
    return text.translate(str.maketrans("oue", "aai"))


def is_city(unit: dict[str, Any]) -> bool:
    return bool(re.search(r"city$|\bcity\b", unit["Klassifikator_en"].lower())
                or re.search(r"\bshahri?\b|\bshahar\b", unit["Klassifikator"]))


def get(url: str) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS),
                                timeout=TIMEOUT) as fh:
        return fh.read()


def download() -> bytes:
    """The data file the download link points to."""
    pointer = json.loads(get(POINTER))
    url = pointer.get("file") or pointer.get("file_2")
    log(f"  {POINTER} -> {url} ({pointer.get('size')}, updated {pointer.get('updated_at')})")
    return get(url)


def years(rows: list[dict[str, Any]]) -> list[str]:
    return sorted(k for k in rows[0] if re.fullmatch(r"\d{4}", k))


def first_year(unit: dict[str, Any], span: list[str]) -> str | None:
    return next((y for y in span if unit.get(y)), None)


def shapes() -> dict[str, list[dict[str, Any]]]:
    """The map's second-level shapes in Uzbekistan, by the name of their region."""
    parents = {e["id"]: e["name"] for e in read_json(SITE / "admin1" / shard_name("UZB"), [])}
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entity in read_json(SITE / "admin2" / shard_name("UZB"), []):
        out[parents.get(entity.get("parent"), "")].append(entity)
    return out


def match(unit: dict[str, Any], region: str,
          by_region: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """The shapes a unit could be, in its region (and where else it may be filed)."""
    pool = [e for r in (region, *ALSO_IN.get(region, ())) for e in by_region.get(r, [])]
    declared = DECLARED.get(unit["Klassifikator_en"])
    if declared:
        return [e for e in pool if e["name"] == declared]
    city = is_city(unit)
    names = {key(unit["Klassifikator_en"]), key(unit["Klassifikator"])}
    return [e for e in pool
            if key(e["name"]) in names and ("city" in e["name"].lower()) == city]


def sources_of(new: dict[str, Any], siblings: list[dict[str, Any]],
               span: list[str]) -> list[tuple[dict[str, Any], float]]:
    """The units a new one was carved from: what each lost the year it appeared."""
    year = first_year(new, span)
    before = span[span.index(year) - 1]
    out = []
    for other in siblings:
        if other is new or not other.get(before) or not other.get(year):
            continue
        lost = other[before] - other[year]
        if lost > ALSO_SOURCE * new[year]:
            out.append((other, lost))
    return out


def build(data: list[dict[str, Any]], by_region: dict[str, list[dict[str, Any]]]
          ) -> tuple[list[dict[str, Any]], list[str]]:
    span = years(data)
    latest = span[-1]
    region_of = {u["Code"]: u["Klassifikator_en"] for u in data if len(u["Code"]) == 4}
    units = [u for u in data if len(u["Code"]) > 4 and u.get(latest)]
    source = (f"Statistics Agency of Uzbekistan, SIAT indicator {CODE}, permanent "
              f"population on 1 January {latest}")
    cite = [{"field": "population", "name": source, "url": PAGE, "license": LICENCE}]
    notes: list[str] = []

    # Every unit to the shape it is, where exactly one answers.
    placed: dict[str, dict[str, Any]] = {}
    claims: dict[str, list[str]] = defaultdict(list)
    for unit in units:
        region = REGION[region_of[unit["Code"][:4]]]
        found = match(unit, region, by_region)
        if len(found) == 1:
            placed[unit["Code"]] = found[0]
            claims[found[0]["id"]].append(unit["Code"])
        unit["_region"] = region
    for shape_id, codes in claims.items():
        if len(codes) > 1:
            notes.append(f"{shape_id}: claimed by {codes}; none kept")
            for code in codes:
                placed.pop(code, None)

    # What the boundary file does not draw, and whose ground it is on.
    extra: dict[str, list[dict[str, Any]]] = defaultdict(list)   # shape id -> units
    refused: dict[str, str] = {}                                  # shape id -> why
    shape_of = {u["Code"]: s for u in units if (s := placed.get(u["Code"]))}
    for unit in units:
        if unit["Code"] in placed:
            continue
        name = unit["Klassifikator_en"]
        people = f"{unit[latest] * 1000:,.0f}"
        if name in UNDRAWN:
            for target in UNDRAWN[name]:
                for shape in (s for s in shape_of.values() if s["name"] == target):
                    refused[shape["id"]] = (
                        f"{name} ({people} people), which the agency counts on its own "
                        f"and the boundary file does not draw, lies on the border of "
                        f"{' and '.join(UNDRAWN[name])}; which of them holds its ground "
                        f"cannot be told, so neither takes the agency's figure.")
            continue
        year = first_year(unit, span)
        if year == span[0]:
            notes.append(f"{name}: not drawn and in the series from its start; "
                         f"no shape takes it")
            continue
        siblings = [u for u in units if u["Code"][:4] == unit["Code"][:4]]
        found = sources_of(unit, siblings, span)
        drawn = [(u, lost) for u, lost in found if u["Code"] in placed]
        if (len(found) == 1 and drawn
                and found[0][1] >= SOLE_SOURCE * unit[year]):
            extra[placed[drawn[0][0]["Code"]]["id"]].append(unit)
            notes.append(f"{name}: carved from {drawn[0][0]['Klassifikator_en']} in {year}")
            continue
        for source_unit, _ in drawn:
            refused[placed[source_unit["Code"]]["id"]] = (
                f"Part of this district became {name} in {year}, which the boundary "
                f"file does not draw, together with part of "
                + ", ".join(u["Klassifikator_en"] for u, _ in found
                            if u is not source_unit)
                + "; how much came from each is not published, so the agency's "
                  "figure is left out.")
        notes.append(f"{name}: carved from {[u['Klassifikator_en'] for u, _ in found]} "
                     f"in {year}; those shapes left blank")

    rows: list[dict[str, Any]] = []
    for code, region in region_of.items():
        if region not in REGION:
            continue
        unit = next(u for u in data if u["Code"] == code)
        rows.append(record(f"UZB-SIAT-{code}", REGION[region], level="admin1",
                           parent="UZB", country="UZB",
                           aliases=[region, unit["Klassifikator"]],
                           population=measure(round(unit[latest] * 1000), year=int(latest),
                                              source=source),
                           sources=cite))
    parents = {e["id"]: r for r, es in by_region.items() for e in es}
    for unit in units:
        shape = placed.get(unit["Code"])
        if shape is None:
            continue
        parts = [unit, *extra.get(shape["id"], [])]
        why = refused.get(shape["id"])
        if why:
            population = gap(NOT_AVAILABLE, why)
        else:
            value = round(sum(p[latest] for p in parts) * 1000)
            population = measure(value, year=int(latest), source=source)
            if len(parts) > 1:
                population["note"] = (
                    f"The boundary file draws this district as it was before "
                    + " and ".join(f"{p['Klassifikator_en']} ({p[latest] * 1000:,.0f})"
                                   for p in parts[1:])
                    + " was carved out of it; the figure is the two together, from "
                      "the same table and year.")
        rows.append(record(f"UZB-SIAT-{unit['Code']}", shape["name"], level="admin2",
                           parent="UZB", country="UZB", parent_name=parents[shape["id"]],
                           aliases=[unit["Klassifikator_en"], unit["Klassifikator"]],
                           population=population, sources=[] if why else cite))
    return rows, notes


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dump", action="store_true", help="save the agency's JSON and stop")
    ap.add_argument("--offline", action="store_true", help="read the saved JSON")
    args = ap.parse_args()
    blob = DUMP.read_bytes() if args.offline else download()
    if args.dump:
        DUMP.parent.mkdir(parents=True, exist_ok=True)
        DUMP.write_bytes(blob)
        log(f"  wrote {DUMP.relative_to(ROOT)}")
        return 0
    data = json.loads(blob)[0]["data"]
    rows, notes = build(data, shapes())
    for line in notes:
        log(f"  {line}")
    districts = [r for r in rows if r["level"] == "admin2"]
    filled = sum(1 for r in districts if "value" in r["population"])
    log(f"  {len(rows) - len(districts)} regions, {len(districts)} districts "
        f"({filled} with a figure, {len(districts) - filled} left blank with the reason)")
    write_json(OUT, rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
