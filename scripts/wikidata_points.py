#!/usr/bin/env python3
"""Which of the map's polygons an official code names, by where Wikidata puts it.

A statistics office keys its tables by its own codes -- Japan's JIS municipal
codes, China's administrative division codes -- and names its units in its own
script. The map's polygons carry geoBoundaries' romanised names, and for some
units (24 of Japan's) no name at all. Joined by name, Japan's 1,731
municipalities and China's 2,370 counties found almost nothing.

Wikidata holds the bridge: an item for each unit with the office's code and a
coordinate. The coordinate put in the map's polygons says which polygon the
code is; the item's name agreeing with the polygon's is the second, separate
test. A code is only bound to a polygon when both say the same thing and no
other item of the level says it too -- a polygon holding two items that both
pass keeps neither.

``--fetch ISO3 PROPERTY`` (runner, where query.wikidata.org answers) writes
every current item of the country carrying the property, with its label,
code, coordinate and latest population, to data/raw/wikidata_points/.

Without it, the items are placed and ``data/processed/code_shapes.json``
gains ``{ISO3: {code: {shape_id, level, qid, name}}}``. ``--populations``
also writes the items' Wikidata populations as records bound to their
polygons (data/processed/wikidata_points_<level>.json), for the units no
office table reaches.

Usage:
    python -m scripts.wikidata_points --fetch JPN P429
    python -m scripts.wikidata_points JPN:P429:6:5 CHN:P442:6:6 --populations
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import NOT_AVAILABLE, PROCESSED, RAW, gap, log, measure, read_json, write_json  # noqa: E402

DEST = RAW / "wikidata_points"
BOUNDARIES = RAW / "boundaries"
OUT = PROCESSED / "code_shapes.json"

QUERY = """
SELECT ?item ?itemLabel ?code ?coord ?pop ?popTime ?pinyin WHERE {
  ?item wdt:%(prop)s ?code ; wdt:P17 wd:%(country)s ; wdt:P625 ?coord .
  FILTER NOT EXISTS { ?item wdt:P576 ?gone . }
  OPTIONAL { ?item wdt:P1721 ?pinyin . }
  OPTIONAL { ?item p:P1082 ?st . ?st ps:P1082 ?pop ; wikibase:rank ?rank .
             FILTER(?rank != wikibase:DeprecatedRank)
             FILTER NOT EXISTS { ?st pq:P518 ?part . }
             OPTIONAL { ?st pq:P585 ?popTime . } }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en,mul". }
}
"""

# Words that name a unit's kind rather than the unit, in English labels and
# in the map's romanised names, so "Aba County" and "Abaxian" compare as
# "aba" and "aba".
KIND = re.compile(
    r"(autonomous|county|district|city|banner|prefecture|municipality|town|"
    r"village|ward|league|region|special|new area|forest area|"
    r"zizhixian|zizhiqi|xian|shi|qu|qi|linqu|tequ|"
    r"-shi|-ku|-machi|-cho|-mura|-son)$")


def folded(text: str | None) -> str:
    text = unicodedata.normalize("NFKD", text or "").lower()
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9 -]", "", text).strip()


def core(text: str | None) -> str:
    """The name without its kind words, run together."""
    words = folded(text)
    for _ in range(3):
        stripped = KIND.sub("", words).strip(" -")
        if stripped == words:
            break
        words = stripped
    return words.replace(" ", "").replace("-", "")


def agrees(label: str, shape_name: str) -> bool:
    a, b = core(label), core(shape_name)
    return bool(a and b) and (a == b or (len(a) >= 4 and len(b) >= 4 and (a.startswith(b) or b.startswith(a))))


def fetch(iso3: str, prop: str) -> None:
    from fetch_wikidata import country_qids, sparql, value
    country = country_qids()[iso3]
    rows = sparql(QUERY % {"prop": prop, "country": country}, cache=False, retries=2)
    items: dict[str, dict] = {}
    for row in rows:
        qid = value(row, "item")
        m = re.match(r"Point\(([-\d.]+) ([-\d.]+)\)", value(row, "coord") or "")
        if not qid or not m:
            continue
        item = items.setdefault(qid, {"qid": qid, "label": value(row, "itemLabel"),
                                      "code": value(row, "code"),
                                      "lon": float(m.group(1)), "lat": float(m.group(2))})
        if value(row, "pinyin"):
            item.setdefault("alt", [])
            if value(row, "pinyin") not in item["alt"]:
                item["alt"].append(value(row, "pinyin"))
        pop, when = value(row, "pop"), value(row, "popTime")
        if pop and (item.get("pop_year") or "") <= (when or ""):
            item["population"] = int(float(pop))
            item["pop_year"] = when or ""
    DEST.mkdir(parents=True, exist_ok=True)
    out = DEST / f"{iso3}_{prop}.json"
    out.write_text(json.dumps(sorted(items.values(), key=lambda r: r["qid"]),
                              ensure_ascii=False), encoding="utf-8")
    log(f"{iso3} {prop}: {len(items)} items -> {out}")


def shapes_of(iso3: str) -> list[dict]:
    import fiona
    from shapely.geometry import shape
    out = []
    for level, name in (("admin1", "ADM1"), ("admin2", "ADM2")):
        with fiona.open(BOUNDARIES / f"geoBoundariesCGAZ_{name}.gpkg") as src:
            for feat in src:
                p = feat["properties"]
                if p["shapeGroup"] == iso3 and feat["geometry"]:
                    out.append({"level": level, "id": p["shapeID"], "name": p.get("shapeName"),
                                "geom": shape(feat["geometry"])})
    return out


def place(iso3: str, prop: str, length: int, keep: int) -> tuple[dict[str, dict], list[dict]]:
    """code -> polygon, for the items whose place and name agree."""
    from shapely import STRtree
    from shapely.geometry import Point
    items = json.loads((DEST / f"{iso3}_{prop}.json").read_text(encoding="utf-8"))
    shapes = shapes_of(iso3)
    tree = STRtree([s["geom"] for s in shapes])
    by_shape: dict[str, list[dict]] = defaultdict(list)
    for item in items:
        # Exactly the level's length, before anything is cut: a Chinese
        # town's 9- or 12-digit code begins with its county's six, and cut to
        # six it would pass for the county.
        full = re.sub(r"\D", "", item.get("code") or "")
        if len(full) != length:
            continue
        code = full[:keep]
        item["code"] = code
        for i in tree.query(Point(item["lon"], item["lat"]), predicate="within"):
            s = shapes[i]
            names = [item.get("label") or "", *(item.get("alt") or [])]
            if any(agrees(n, s["name"] or "") for n in names):
                by_shape[s["id"]].append({**item, "level": s["level"], "shape": s})
    bound: dict[str, dict] = {}
    refused = 0
    for shape_id, hits in by_shape.items():
        codes = {h["code"] for h in hits}
        if len(codes) > 1:
            refused += 1
            continue
        h = hits[0]
        bound.setdefault(h["code"], {"shape_id": shape_id, "level": h["level"], "qid": h["qid"],
                                     "name": h["shape"]["name"], "label": h["label"],
                                     "population": h.get("population"),
                                     "pop_year": h.get("pop_year")})
    levels = defaultdict(int)
    for entry in bound.values():
        levels[entry["level"]] += 1
    log(f"{iso3} {prop}: {len(items)} items; {len(bound)} codes bound to a polygon "
        f"{dict(levels)}; {refused} polygons held two codes that both agree and were left")
    return bound, items


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fetch", nargs=2, metavar=("ISO3", "PROPERTY"))
    ap.add_argument("specs", nargs="*",
                    help="ISO3:PROPERTY:LENGTH:KEEP -- codes of exactly LENGTH digits, "
                         "keyed by their first KEEP (Japan's check digit is dropped)")
    ap.add_argument("--populations", action="store_true")
    args = ap.parse_args()
    if args.fetch:
        fetch(args.fetch[0].upper(), args.fetch[1])
        return 0
    table = read_json(OUT, {}) or {}
    records: dict[str, list] = defaultdict(list)
    for spec in args.specs:
        iso3, prop, length, keep = spec.split(":")
        bound, _ = place(iso3.upper(), prop, int(length), int(keep))
        table[iso3.upper()] = {code: {k: v for k, v in e.items() if k not in ("population", "pop_year")}
                               for code, e in sorted(bound.items())}
        if args.populations:
            for code, e in bound.items():
                if not e.get("population"):
                    continue
                year = int(e["pop_year"][:4]) if e.get("pop_year") else None
                records[e["level"]].append({
                    "id": f"{iso3.upper()}-WDP-{e['qid']}", "wikidata": e["qid"], "level": e["level"],
                    "name": e["name"], "parent": iso3.upper(), "country": iso3.upper(),
                    "match_by": "shape_id", "shape_id": e["shape_id"],
                    "population": measure(e["population"], year=year, source="Wikidata (CC0)"),
                    "median_age": gap(NOT_AVAILABLE), "sex_ratio": gap(NOT_AVAILABLE),
                    "sources": [{"field": "population", "name": "Wikidata",
                                 "url": f"https://www.wikidata.org/wiki/{e['qid']}",
                                 "license": "CC0"}],
                })
    write_json(OUT, table)
    for level, rows in records.items():
        write_json(PROCESSED / f"wikidata_points_{level}.json", rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
