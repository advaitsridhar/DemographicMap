#!/usr/bin/env python3
"""GeoNames populated places (CC BY 4.0) -- the largest settlement in every unit.

Natural Earth names a largest settlement for countries and for the
first-order units it knows by name; below that, 49,000 second-order units had
none. GeoNames' ``cities500`` lists every populated place of 500 people or
more, and every seat of an administrative division, with a coordinate and a
population: placed in the map's own shapes, the most populous place inside
each one is its largest settlement.

Two runs, because the shapes and the list live in different places:

``--fetch`` (on a runner, where download.geonames.org answers) reads the dump
and keeps the columns this uses, as ``data/raw/geonames/places.tsv.gz``.

Without it, the places are put in the CGAZ polygons of both levels and the
result written to ``data/processed/geonames_settlements.json``, keyed by
shapeID.

A place is only credited to a shape it can be shown to belong to. A CGAZ
polygon is simplified, so a town a few hundred metres from a boundary can land
in its neighbour -- and a named town that is not in the unit is worse than no
name. GeoNames files each place under its own first- and second-order codes,
so every shape has a plurality of codes among the places inside it; a place
whose code disagrees with its shape's plurality has most likely crossed a
boundary and is passed over. The second-order check is made only where the
country's codes line up with the map's shapes (the plurality holds most of
the places), since elsewhere GeoNames' units are not the map's.

Sections of a city (PPLX), and historical, abandoned or destroyed places, are
never counted: a borough's population is not a settlement's.

Usage:
    python -m scripts.fetch_geonames --fetch      # runner
    python -m scripts.fetch_geonames              # local, needs the CGAZ files
"""
from __future__ import annotations

import argparse
import csv
import gzip
import io
import sys
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import PROCESSED, RAW, http_get, log, write_json  # noqa: E402

URL = "https://download.geonames.org/export/dump/cities500.zip"
COUNTRY_INFO = "https://download.geonames.org/export/dump/countryInfo.txt"
DEST = RAW / "geonames"
PLACES = DEST / "places.tsv.gz"
OUT = PROCESSED / "geonames_settlements.json"
BOUNDARIES = RAW / "boundaries"
SOURCE = "GeoNames (CC BY 4.0)"

# Feature codes of places that are settlements in their own right.
SETTLEMENT = {"PPL", "PPLA", "PPLA2", "PPLA3", "PPLA4", "PPLA5", "PPLC",
              "PPLG", "PPLL", "PPLS", "PPLF", "PPLR"}
# Seats of government, down to the second order.
SEATS = {"PPLC", "PPLA", "PPLA2"}
# A place this many times its unit's own count is a city the unit is only part
# of, or a place across a boundary: no settlement is named rather than it.
SPANS = 1.5
COLUMNS = ("geonameid", "name", "lat", "lon", "code", "iso3", "admin1",
           "admin2", "population")
# A country's second-order codes are taken to line up with the map's shapes
# when, across its shapes, the plurality code holds this share of the places.
ALIGNED = 0.8


def fetch() -> None:
    iso = {}
    for line in http_get(COUNTRY_INFO).splitlines():
        if line and not line.startswith("#"):
            parts = line.split("\t")
            iso[parts[0]] = parts[1]
    raw = http_get(URL, cache=False, timeout=600, binary=True)
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        text = zf.read("cities500.txt").decode("utf-8")
    DEST.mkdir(parents=True, exist_ok=True)
    kept = 0
    with gzip.open(PLACES, "wt", encoding="utf-8", newline="") as fh:
        out = csv.writer(fh, delimiter="\t", lineterminator="\n")
        out.writerow(COLUMNS)
        for line in text.splitlines():
            f = line.split("\t")
            if len(f) < 15 or f[6] != "P" or f[7] not in SETTLEMENT:
                continue
            population = int(f[14] or 0)
            # A seat with no population is kept: it says the unit's own
            # town is there, of a size GeoNames does not know.
            if f[8] not in iso or (population <= 0 and f[7] not in SEATS):
                continue
            out.writerow((f[0], f[1], f[4], f[5], f[7], iso[f[8]], f[10], f[11], population))
            kept += 1
    log(f"kept {kept} settlements with a population -> {PLACES}")


def read_places() -> list[dict]:
    with gzip.open(PLACES, "rt", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh, delimiter="\t"))
    for row in rows:
        row["lat"], row["lon"] = float(row["lat"]), float(row["lon"])
        row["population"] = int(row["population"])
    return rows


def contain(level: str, places: list[dict]) -> dict[str, list[dict]]:
    """shapeID -> the places whose point lies in that shape (same country)."""
    import fiona
    from shapely import STRtree, points
    from shapely.geometry import shape as to_shape

    ids, groups, geoms = [], [], []
    with fiona.open(BOUNDARIES / f"geoBoundariesCGAZ_{level}.gpkg") as src:
        for feat in src:
            props = feat["properties"]
            if not feat["geometry"]:
                continue
            ids.append(props["shapeID"])
            groups.append(props["shapeGroup"])
            geoms.append(to_shape(feat["geometry"]))
    tree = STRtree(geoms)
    pts = points([(p["lon"], p["lat"]) for p in places])
    place_idx, shape_idx = tree.query(pts, predicate="within")
    inside: dict[str, list[dict]] = defaultdict(list)
    for pi, si in zip(place_idx, shape_idx):
        place = places[pi]
        if groups[si] == place["iso3"]:
            inside[ids[si]].append(place)
    return inside


def plurality(rows: list[dict], key: str) -> tuple[str | None, float]:
    counts = Counter(r[key] for r in rows if r[key])
    if not counts:
        return None, 0.0
    code, n = counts.most_common(1)[0]
    return code, n / sum(counts.values())


def aligned_countries(inside: dict[str, list[dict]]) -> set[str]:
    """Countries whose GeoNames second-order codes follow the map's shapes."""
    agree, total = Counter(), Counter()
    for rows in inside.values():
        if not rows:
            continue
        code, _ = plurality(rows, "admin2")
        iso3 = rows[0]["iso3"]
        for r in rows:
            if r["admin2"]:
                total[iso3] += 1
                agree[iso3] += r["admin2"] == code
    return {iso3 for iso3 in total if agree[iso3] / total[iso3] >= ALIGNED}


def largest(rows: list[dict], check_admin2: bool, seats: set[str],
            unit_population: int | None = None) -> tuple[dict | None, str | None]:
    """The most populous place that belongs, or None and why not.

    ``seats`` are the feature codes of this level's seats. When one of them in
    the unit has no population, the unit's own town is of unknown size, and a
    smaller place named as the largest would be wrong; so unless the winner
    is itself a seat, nothing is named.
    """
    code1, _ = plurality(rows, "admin1")
    code2, _ = plurality(rows, "admin2") if check_admin2 else (None, 0)
    belongs = [r for r in rows
               if not (code1 and r["admin1"] and r["admin1"] != code1)
               and not (code2 and r["admin2"] and r["admin2"] != code2)]
    counted = sorted((r for r in belongs if r["population"] > 0), key=lambda r: -r["population"])
    if not counted:
        return None, "no place with a population"
    best = counted[0]
    unsized = [r for r in belongs if r["population"] <= 0 and r["code"] in seats]
    if unsized and best["code"] not in seats:
        return None, f"its seat {unsized[0]['name']} has no population in GeoNames"
    if unit_population and best["population"] > SPANS * unit_population:
        return None, (f"{best['name']} ({best['population']:,}) is more than the unit "
                      f"({unit_population:,}): a city it is part of, or across a boundary")
    return best, None


def unit_populations() -> dict[str, int]:
    """shapeID -> the population the map already gives the unit."""
    import glob
    import json
    site = PROCESSED.parent.parent / "site" / "data"
    out: dict[str, int] = {}
    for path in glob.glob(str(site / "admin[12]" / "*.json")):
        for rec in json.load(open(path, encoding="utf-8")):
            value = (rec.get("population") or {}).get("value") if isinstance(rec.get("population"), dict) else None
            if value:
                out[rec.get("shape_id") or rec["id"]] = value
    return out


def assign() -> None:
    places = read_places()
    log(f"{len(places)} places")
    populations = unit_populations()
    out: dict[str, dict] = {}
    for level, seats in (("ADM1", {"PPLC", "PPLA"}), ("ADM2", SEATS)):
        inside = contain(level, places)
        aligned = aligned_countries(inside) if level == "ADM2" else set()
        found = 0
        why_not: Counter = Counter()
        for shape_id, rows in inside.items():
            unit_pop = populations.get(shape_id)
            best, why = largest(rows, level == "ADM2" and rows[0]["iso3"] in aligned,
                                seats, unit_pop)
            if not best:
                why_not[why.split(" ")[0] if why.startswith("no ") else
                        ("unsized seat" if "no population in GeoNames" in why else "spans")] += 1
                continue
            found += 1
            entry = {
                "name": best["name"],
                "coordinates": [round(best["lon"], 5), round(best["lat"], 5)],
                "feature_code": best["code"],
                "geonameid": best["geonameid"],
                "source": SOURCE,
            }
            # GeoNames' figure is often an older census than the unit's own;
            # a town larger than the unit it is in reads as an error, so the
            # name stands without it.
            if not unit_pop or best["population"] <= unit_pop:
                entry["population"] = best["population"]
            out[shape_id] = entry
        log(f"{level}: {found} shapes with a settlement; none named for {dict(why_not)}; "
            f"admin2 codes line up in {len(aligned)} countries")
    write_json(OUT, out, compact=True)
    log(f"-> {OUT}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fetch", action="store_true", help="download the dump (runner)")
    args = ap.parse_args()
    if args.fetch:
        fetch()
    else:
        assign()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
