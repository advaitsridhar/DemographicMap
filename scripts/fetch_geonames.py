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
            if population <= 0 or f[8] not in iso:
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


def largest(rows: list[dict], check_admin2: bool) -> tuple[dict | None, int]:
    """The most populous place that belongs; and how many larger were refused."""
    code1, _ = plurality(rows, "admin1")
    code2, _ = plurality(rows, "admin2") if check_admin2 else (None, 0)
    refused = 0
    for row in sorted(rows, key=lambda r: -r["population"]):
        if code1 and row["admin1"] and row["admin1"] != code1:
            refused += 1
            continue
        if code2 and row["admin2"] and row["admin2"] != code2:
            refused += 1
            continue
        return row, refused
    return None, refused


def assign() -> None:
    places = read_places()
    log(f"{len(places)} places")
    out: dict[str, dict] = {}
    for level in ("ADM1", "ADM2"):
        inside = contain(level, places)
        aligned = aligned_countries(inside) if level == "ADM2" else set()
        found = refused_any = 0
        for shape_id, rows in inside.items():
            best, refused = largest(rows, level == "ADM2" and rows[0]["iso3"] in aligned)
            refused_any += bool(refused)
            if not best:
                continue
            found += 1
            out[shape_id] = {
                "name": best["name"],
                "population": best["population"],
                "coordinates": [round(best["lon"], 5), round(best["lat"], 5)],
                "feature_code": best["code"],
                "geonameid": best["geonameid"],
                "source": SOURCE,
            }
        log(f"{level}: {found} shapes with a settlement; {refused_any} passed over a larger "
            f"place filed elsewhere; admin2 codes line up in {len(aligned)} countries")
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
