#!/usr/bin/env python3
"""Subnational attributes from Wikidata SPARQL (CC0).

Wikidata is the only source that covers *every* country's admin-1 and admin-2
units with a single query shape, so it supplies the baseline population,
capital, inception and coordinates that the national statistical agencies then
override where they publish something better.

Design notes:

* Entity classes differ per country ("state of India" vs "province of China"),
  so the walk is structural instead: start from the country item and follow
  P150 (contains administrative territorial entity), then P131 (located in the
  administrative territorial entity) for the level below.  No per-country class
  table to maintain.
* Every optional field is wrapped in ``OPTIONAL`` so an entity missing a
  population is still returned rather than silently dropped.
* Population statements carry qualifiers; we ask for P585 (point in time) and
  keep the most recent statement per entity, recording its year.
* The public endpoint enforces a 60s query timeout and asks for a descriptive
  User-Agent, so queries are issued per country and retried with backoff.

Usage:
    python scripts/fetch_wikidata.py --level admin1
    python scripts/fetch_wikidata.py --level admin2 --countries IND BRA
"""

from __future__ import annotations

import argparse
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (  # noqa: E402
    NOT_AVAILABLE, PROCESSED, RAW, gap, http_get, log, measure, read_json, write_json,
)

ENDPOINT = "https://query.wikidata.org/sparql"

# One hop down the administrative tree from a country (?country = wd:Qxxx).
ADMIN1_QUERY = """
SELECT ?unit ?unitLabel ?pop ?popTime ?capitalLabel ?coord ?inception ?iso ?typeLabel WHERE {
  VALUES ?country { wd:%(qid)s }
  ?country wdt:P150 ?unit .
  OPTIONAL { ?unit p:P1082 ?popSt .
             ?popSt ps:P1082 ?pop .
             OPTIONAL { ?popSt pq:P585 ?popTime . } }
  OPTIONAL { ?unit wdt:P36 ?capital . }
  OPTIONAL { ?unit wdt:P625 ?coord . }
  OPTIONAL { ?unit wdt:P571 ?inception . }
  OPTIONAL { ?unit wdt:P300 ?iso . }
  OPTIONAL { ?unit wdt:P31 ?type . }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en,mul". }
}
"""

# Two hops down: every unit whose P131 is one of the country's admin-1 units.
ADMIN2_QUERY = """
SELECT ?unit ?unitLabel ?parent ?parentLabel ?pop ?popTime ?capitalLabel ?coord WHERE {
  VALUES ?country { wd:%(qid)s }
  ?country wdt:P150 ?parent .
  ?unit wdt:P131 ?parent .
  ?unit wdt:P31/wdt:P279* wd:Q56061 .        # instance of an administrative territorial entity
  OPTIONAL { ?unit p:P1082 ?popSt .
             ?popSt ps:P1082 ?pop .
             OPTIONAL { ?popSt pq:P585 ?popTime . } }
  OPTIONAL { ?unit wdt:P36 ?capital . }
  OPTIONAL { ?unit wdt:P625 ?coord . }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en,mul". }
}
"""

# ISO3 -> Wikidata country item.  Resolved live when the lookup misses.
COUNTRY_QID_QUERY = """
SELECT ?country ?iso3 WHERE {
  ?country wdt:P31 wd:Q6256 ; wdt:P298 ?iso3 .
}
"""


def sparql(query: str, *, cache: bool = True) -> list[dict[str, Any]]:
    url = ENDPOINT + "?" + urllib.parse.urlencode({"format": "json", "query": query})
    payload = http_get(url, cache=cache, timeout=90,
                       headers={"Accept": "application/sparql-results+json"})
    import json as _json
    data = _json.loads(payload)
    return data.get("results", {}).get("bindings", [])


def value(row: dict[str, Any], key: str) -> str | None:
    node = row.get(key)
    if not node:
        return None
    val = node.get("value")
    if val and node.get("type") == "uri" and val.startswith("http://www.wikidata.org/entity/"):
        return val.rsplit("/", 1)[-1]
    return val


def parse_point(wkt: str | None) -> list[float] | None:
    if not wkt or not wkt.startswith("Point("):
        return None
    try:
        lon, lat = wkt[6:-1].split()
        return [round(float(lon), 5), round(float(lat), 5)]
    except ValueError:
        return None


def country_qids() -> dict[str, str]:
    cached = read_json(RAW / "codes" / "wikidata_countries.json", None)
    if cached:
        return cached
    rows = sparql(COUNTRY_QID_QUERY)
    out = {value(r, "iso3"): value(r, "country") for r in rows if value(r, "iso3")}
    write_json(RAW / "codes" / "wikidata_countries.json", out)
    return out


def collapse(rows: list[dict[str, Any]], *, level: str, iso3: str) -> list[dict[str, Any]]:
    """One record per unit, keeping the most recent population statement."""
    units: dict[str, dict[str, Any]] = {}
    for row in rows:
        qid = value(row, "unit")
        if not qid:
            continue
        name = value(row, "unitLabel")
        if not name or name == qid:      # unlabelled item: not useful in a UI
            continue
        rec = units.setdefault(qid, {
            "id": f"{iso3}-WD-{qid}",
            "wikidata": qid,
            "level": level,
            "name": name,
            "parent": value(row, "parent") or iso3,
            "parent_name": value(row, "parentLabel"),
            "country": iso3,
            "capital": value(row, "capitalLabel"),
            "coordinates": parse_point(value(row, "coord")),
            "inception": (value(row, "inception") or "")[:10] or None,
            "iso_3166_2": value(row, "iso"),
            "population": None,
            "_pop_year": None,
        })
        pop_raw = value(row, "pop")
        if pop_raw is None:
            continue
        try:
            pop = int(float(pop_raw))
        except ValueError:
            continue
        year = (value(row, "popTime") or "")[:4]
        year_i = int(year) if year.isdigit() else None
        if rec["_pop_year"] is None or (year_i or 0) >= (rec["_pop_year"] or 0):
            rec["population"] = pop
            rec["_pop_year"] = year_i

    out = []
    for rec in units.values():
        pop, year = rec.pop("population"), rec.pop("_pop_year")
        rec["population"] = (measure(pop, year=year, source="Wikidata (CC0)")
                             if pop else gap(NOT_AVAILABLE, "No P1082 statement on Wikidata."))
        for key in ("capital", "coordinates", "iso_3166_2", "inception"):
            if rec[key] is None:
                rec[key] = gap(NOT_AVAILABLE)
        rec["sources"] = [{"field": "population/capital/coordinates", "name": "Wikidata",
                           "url": f"https://www.wikidata.org/wiki/{rec['wikidata']}",
                           "license": "CC0"}]
        out.append(rec)
    out.sort(key=lambda r: r["name"])
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--level", default="admin1", choices=["admin1", "admin2"])
    ap.add_argument("--countries", nargs="*", help="ISO3 codes; default is every country")
    ap.add_argument("--sleep", type=float, default=1.0, help="pause between queries (be polite)")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    qids = country_qids()
    codes = [c.upper() for c in (args.countries or sorted(qids))]
    # Wikidata's P298 for Kosovo is XKS; geoBoundaries uses XKX. Normalise so
    # the join buckets the records with the shapes instead of beside them.
    iso3_alias = {"XKS": "XKX"}
    query = ADMIN1_QUERY if args.level == "admin1" else ADMIN2_QUERY

    records: list[dict[str, Any]] = []
    missing: list[str] = []
    for iso3 in codes:
        qid = qids.get(iso3)
        if not qid:
            missing.append(iso3)
            continue
        try:
            rows = sparql(query % {"qid": qid})
        except Exception as exc:
            log(f"  {iso3}: query failed ({exc})")
            missing.append(iso3)
            continue
        got = collapse(rows, level=args.level, iso3=iso3_alias.get(iso3, iso3))
        log(f"  {iso3}: {len(got)} {args.level} units")
        records.extend(got)
        time.sleep(args.sleep)

    # An empty file is not an answer. When every country asked for failed --
    # a Wikidata timeout looks exactly like a country with no units -- writing
    # [] would leave an artefact that reads as "checked, found nothing" and
    # would quietly replace a good file from a previous run.
    if not records and missing:
        raise SystemExit(
            f"every query failed ({', '.join(missing[:30])}); nothing written. "
            "Wikidata's endpoint rate-limits and times out under load; retry "
            "rather than treating this as an empty result.")

    out = args.out or PROCESSED / f"wikidata_{args.level}.json"
    write_json(out, records)
    if missing:
        log(f"  no data for {len(missing)} countries: {', '.join(missing[:30])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
