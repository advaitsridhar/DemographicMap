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
shapeID: the place, or ``{"none": why}`` for a shape where none is named.

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
SEATS_OUT = PROCESSED / "geonames_seats.json"
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


# How far across a line a place may sit and still be its own unit's: the CGAZ
# outlines are simplified, and a coastal town can land in the sea (Akcaabat)
# or a seat a few hundred metres inside its neighbour (Adrianopolis).
NEAR = 0.03  # degrees, about 3 km
# A shape's code is only a test of a place once enough places say what it is.
QUORUM, MAJORITY = 3, 0.6


def folded(text: str | None) -> str:
    import unicodedata
    text = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in text if not unicodedata.combining(c) and c.isalnum()).lower()


def code_of(place: dict, level: str) -> tuple:
    return (place["admin1"],) if level == "ADM1" else (place["admin1"], place["admin2"])


def contain(level: str, places: list[dict], aligned: set[str] | None = None) -> dict[str, list[dict]]:
    """shapeID -> the places that are that shape's, by outline and by code.

    A place inside a shape is that shape's, unless the shape's places agree on
    a code and the place's is another -- then it has crossed a line. A place
    that has crossed, or that no shape holds, goes to the shape within
    ``NEAR`` whose places share its code; failing that, one no shape holds
    goes to the nearest within ``NEAR``. Codes are only compared at the
    second level where the country's codes follow the map's shapes.
    """
    import fiona
    from shapely import STRtree, points
    from shapely.geometry import shape as to_shape

    ids, groups, geoms, names = [], [], [], []
    with fiona.open(BOUNDARIES / f"geoBoundariesCGAZ_{level}.gpkg") as src:
        for feat in src:
            props = feat["properties"]
            if not feat["geometry"]:
                continue
            ids.append(props["shapeID"])
            groups.append(props["shapeGroup"])
            geoms.append(to_shape(feat["geometry"]))
            names.append(folded(props.get("shapeName")))
    tree = STRtree(geoms)
    pts = points([(p["lon"], p["lat"]) for p in places])
    held: dict[int, int] = {}
    for pi, si in zip(*tree.query(pts, predicate="within")):
        if groups[si] == places[pi]["iso3"]:
            held[pi] = si

    def compares(si: int) -> bool:
        return level == "ADM1" or (aligned is not None and groups[si] in aligned)

    # Each shape's code, where enough of the places inside it agree.
    votes: dict[int, Counter] = defaultdict(Counter)
    for pi, si in held.items():
        votes[si][code_of(places[pi], level)] += 1
    code: dict[int, tuple] = {}
    for si, counts in votes.items():
        top, n = counts.most_common(1)[0]
        total = sum(counts.values())
        if compares(si) and total >= QUORUM and n / total >= MAJORITY:
            code[si] = top

    inside: dict[str, list[dict]] = defaultdict(list)
    near_idx, near_shape = tree.query(pts, predicate="dwithin", distance=NEAR)
    nearby: dict[int, list[int]] = defaultdict(list)
    for pi, si in zip(near_idx, near_shape):
        if groups[si] == places[pi]["iso3"]:
            nearby[pi].append(si)
    moved = 0
    for pi, place in enumerate(places):
        own = code_of(place, level)
        si = held.get(pi)
        # A seat beside a unit of its own name is that unit's seat, wherever
        # the simplified line puts it: Adrianopolis's lies just inside Ribeira.
        if place["code"] in SEATS:
            namesake = [sj for sj in nearby.get(pi, []) if names[sj] and names[sj] == folded(place["name"])]
            if len(namesake) == 1:
                inside[ids[namesake[0]]].append(place)
                moved += namesake[0] != si
                continue
        if si is not None and (si not in code or code[si] == own):
            inside[ids[si]].append(place)
            continue
        match = [sj for sj in nearby.get(pi, []) if code.get(sj) == own]
        if len(match) == 1:
            inside[ids[match[0]]].append(place)
            moved += 1
        elif si is None and nearby.get(pi):
            closest = min(nearby[pi], key=lambda sj: geoms[sj].distance(pts[pi]))
            if closest not in code or code[closest] == own:
                inside[ids[closest]].append(place)
                moved += 1
    log(f"  {level}: {moved} places moved across a simplified line to their own unit")
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


def largest(rows: list[dict], seats: set[str],
            unit_population: int | None = None) -> tuple[dict | None, str | None]:
    """The most populous of a unit's places, or None and why not.

    ``seats`` are the feature codes of this level's seats. When one of them in
    the unit has no population, the unit's own town is of unknown size, and a
    smaller place named as the largest would be wrong; so unless the winner
    is itself a seat, nothing is named.
    """
    counted = sorted((r for r in rows if r["population"] > 0), key=lambda r: -r["population"])
    if not counted:
        return None, "no place with a population"
    best = counted[0]
    unsized = [r for r in rows if r["population"] <= 0 and r["code"] in seats]
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


# Each level's own seats, and where GeoNames' units are taken to be the map's:
# most polygons hold exactly one, next to none hold two, and where the map
# already names capitals the seats agree with them.
OWN_SEAT = {"ADM1": {"PPLA"}, "ADM2": {"PPLA2"}}
ONE_SEAT, TWO_SEATS, AGREES, COMPARED = 0.6, 0.05, 0.85, 10
# Brazil's municipalities take their seat's name by law -- "A sede do
# municipio tem a categoria de cidade e lhe da o nome" (Decreto-Lei 311 de
# 1938, art. 3) -- and GeoNames does not flag the seats; so there the place
# of the municipality's own name, inside it, is its seat.
NAMESAKE_SEAT = {"BRA"}


def site_units(level: str) -> tuple[dict[str, dict], dict[str, int]]:
    """shapeID -> the unit as built; and units per country, at one level."""
    import glob
    import json
    site = PROCESSED.parent.parent / "site" / "data" / level
    units, count = {}, Counter()
    for path in glob.glob(str(site / "*.json")):
        for rec in json.load(open(path, encoding="utf-8")):
            if rec.get("level") == level:
                units[rec["id"]] = rec
                count[rec["country"]] += 1
    return units, count


def alike(a: str, b: str) -> bool:
    from difflib import SequenceMatcher
    a, b = folded(a), folded(b)
    return bool(a and b) and (a == b or a in b or b in a
                              or SequenceMatcher(None, a, b).ratio() >= 0.8)


def seat_of(level: str, iso3: str, unit_name: str, rows: list[dict]) -> dict | None:
    own = [r for r in rows if r["code"] in OWN_SEAT[level]]
    if len(own) == 1:
        return own[0]
    if own:
        return None
    if iso3 in NAMESAKE_SEAT:
        same = [r for r in rows if folded(r["name"]) == folded(unit_name)]
        return same[0] if len(same) == 1 else None
    # A unit holding its country's or province's seat and no seat of its own
    # level: that town is its seat too, if the unit bears its name (Sacramento
    # County, not the Ibadan North East that holds Ibadan).
    upper = [r for r in rows if r["code"] in ({"PPLC"} if level == "ADM1" else {"PPLA", "PPLC"})]
    if len(upper) == 1 and alike(upper[0]["name"], unit_name):
        return upper[0]
    return None


# Capitals the test flags that were each looked at and kept: Republika
# Srpska's de jure capital is Sarajevo; Lao Cai merged with Yen Bai in 2025 and
# is governed from there, which GeoNames predates; Villa Santa Rosa is Santa
# Rosa de Rio Primero; Chum Saeng is the tambon Wang Chan district is seated in;
# and which of several Guerreros GeoNames holds is not certain.
KEPT_CAPITALS = {("BIH", "Sarajevo"), ("VNM", "Yên Bái"), ("ARG", "Villa Santa Rosa"),
                 ("THA", "Chum Saeng"), ("MEX", "Vicente Guerrero")}


def refuted(level: str, inside: dict[str, list[dict]],
            places: list[dict]) -> dict[str, dict]:
    """shapeID -> a capital a source names that the unit's own seat contradicts.

    Wikidata's capital statements include former capitals at normal rank,
    and a unit with two took whichever row came first: Central Kalimantan
    was given Banjarmasin, South Kalimantan's, and North Sulawesi Gorontalo,
    a province of its own since 2000. A capital outside its unit is not
    wrong by itself -- Kyiv governs Kyiv Oblast from outside it, Chandigarh
    two states -- and a capital spelt another way (Oryol, Orel) is not a
    different place. So a capital is refuted only where the unit holds
    exactly one seat of its own level, under another name; nothing of the
    capital's name stands inside the unit; and a place of that name does
    stand elsewhere in the country -- a real town, somewhere else. The seat
    is what replaces it.
    """
    import re
    units, _ = site_units("admin1" if level == "ADM1" else "admin2")
    named: dict[str, set[str]] = defaultdict(set)
    for place in places:
        named[place["iso3"]].add(folded(place["name"]))
    out = {}
    for shape_id, rows in inside.items():
        unit = units.get(shape_id)
        # What the sources give, before an earlier build corrected it.
        held = (unit.get("capital_refuted") or unit.get("capital")) if unit else None
        if not isinstance(held, str) or re.fullmatch(r"Q\d+", held):
            continue
        if any(alike(held, r["name"]) for r in rows):
            continue
        if folded(held) not in named[unit["country"]] or (unit["country"], held) in KEPT_CAPITALS:
            continue
        own = [r for r in rows if r["code"] in OWN_SEAT[level]]
        if len(own) == 1 and not alike(own[0]["name"], held):
            out[shape_id] = {"refutes": held, "seat": own[0]["name"]}
    return out


def seats(level: str, inside: dict[str, list[dict]]) -> dict[str, dict]:
    """shapeID -> its seat, for the countries whose seats pass the tests."""
    import re
    units, count = site_units("admin1" if level == "ADM1" else "admin2")
    one, two, agree, compared = Counter(), Counter(), Counter(), Counter()
    found: dict[str, tuple[str, dict]] = {}
    for shape_id, rows in inside.items():
        unit = units.get(shape_id)
        if not unit:
            continue
        iso3 = unit["country"]
        own = [r for r in rows if r["code"] in OWN_SEAT[level]]
        one[iso3] += len(own) == 1
        two[iso3] += len(own) >= 2
        seat = seat_of(level, iso3, unit["name"], rows)
        if not seat:
            continue
        held = unit.get("capital")
        if isinstance(held, str) and not re.fullmatch(r"Q\d+", held):
            compared[iso3] += 1
            agree[iso3] += alike(held, seat["name"])
        found[shape_id] = (iso3, seat)
    eligible = set()
    for iso3 in count:
        n = count[iso3]
        if iso3 in NAMESAKE_SEAT or (one[iso3] / n >= ONE_SEAT and two[iso3] / n <= TWO_SEATS):
            if compared[iso3] < COMPARED or agree[iso3] / compared[iso3] >= AGREES:
                eligible.add(iso3)
    refused = sorted(i for i in count if i not in eligible and (one[i] or two[i]))
    log(f"  {level} seats: {len(eligible)} countries pass; refused {len(refused)}: "
        + ", ".join(f"{i} ({one[i]}/{count[i]} one, {two[i]} two, "
                    f"{agree[i]}/{compared[i]} agree)" for i in refused[:25]))
    return {sid: {"name": seat["name"], "coordinates": [round(seat["lon"], 5), round(seat["lat"], 5)],
                  "feature_code": seat["code"], "geonameid": seat["geonameid"], "source": SOURCE}
            for sid, (iso3, seat) in found.items() if iso3 in eligible}


def assign() -> None:
    places = read_places()
    log(f"{len(places)} places")
    populations = unit_populations()
    out: dict[str, dict] = {}
    seat_out: dict[str, dict] = {}
    for level, seat_codes in (("ADM1", {"PPLC", "PPLA"}), ("ADM2", SEATS)):
        aligned = aligned_countries(contain(level, places)) if level == "ADM2" else set()
        inside = contain(level, places, aligned)
        found = 0
        why_not: Counter = Counter()
        for shape_id, rows in inside.items():
            unit_pop = populations.get(shape_id)
            best, why = largest(rows, seat_codes, unit_pop)
            if not best:
                why_not[why.split(" ")[0] if why.startswith("no ") else
                        ("unsized seat" if "no population in GeoNames" in why else "spans")] += 1
                # The build says why the unit has no settlement, rather than
                # leaving a bare gap.
                out[shape_id] = {"none": why}
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
        placed = seats(level, inside)
        seat_out.update(placed)
        wrong = refuted(level, inside, places)
        for shape_id, verdict in wrong.items():
            seat_out.setdefault(shape_id, {}).update(verdict)
        log(f"{level}: {len(placed)} seats; {len(wrong)} capitals named that the unit's "
            f"own seat contradicts")
    write_json(OUT, out, compact=True)
    write_json(SEATS_OUT, seat_out, compact=True)
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
