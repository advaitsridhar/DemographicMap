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
import json
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (  # noqa: E402
    NOT_AVAILABLE, PROCESSED, RAW, forget, gap, http_get, log, measure, read_json,
    write_json,
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
# The same, stripped to what a Wikipedia probe needs: the unit, its label and
# its parent, and nothing else. The three OPTIONAL blocks above -- population
# with its point in time, capital, coordinates -- are what make the full query
# expensive, and on 21 September 2026 they made it unrunnable: a sweep of all
# 218 countries was cancelled at the job's 45-minute limit having reached about
# 25, with Wikidata answering 502, 504 and read-timeout on most of them and
# Austria failing outright after four retries.
#
# This asks for QIDs, and a QID is all that resolves to a Wikipedia article.
#
# It must never be run for a country already in the file. The merge below
# replaces an answered country's records wholesale, so a light answer for
# Mexico would drop the 1,877 populations the full query found there. --light
# refuses such a country by name rather than trusting the caller to remember.
ADMIN2_LIGHT_QUERY = """
SELECT ?unit ?unitLabel ?parent ?parentLabel WHERE {
  VALUES ?country { wd:%(qid)s }
  ?country wdt:P150 ?parent .
  ?unit wdt:P131 ?parent .
  ?unit wdt:P31/wdt:P279* wd:Q56061 .
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en,mul". }
}
"""

ADMIN1_LIGHT_QUERY = """
SELECT ?unit ?unitLabel WHERE {
  VALUES ?country { wd:%(qid)s }
  ?country wdt:P150 ?unit .
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en,mul". }
}
"""

# A second shape for the second level, and why there are two.
#
# ADMIN2_QUERY walks *up*: everything whose P131 is one of the country's
# admin-1 units, narrowed to administrative entities by a P279* walk up the
# class tree. Before that filter the set is enormous -- every village, school,
# protected area and railway station in the country carries P131 to a state --
# and the filter runs over all of it. That, and not the OPTIONAL blocks, is
# the expense. The --light run of 21 September dropped all three OPTIONALs and
# still lost eight of twenty-three countries: AFG, ALB, ARM, AUT, AZE, BLR and
# BOL each came back as valid JSON that stops mid-object several hundred kB
# in, which is WDQS hitting its 60-second limit and abandoning the stream.
#
# This walks *down* instead, by the property the admin-1 query already uses:
# P150, the subdivisions a unit declares. One hop from a handful of parents,
# and it costs almost nothing.
#
# The two are not equivalent and neither is obviously better. P150 is curated
# and can be incomplete; P131 is carried by the members themselves and can
# reach things that are not subdivisions at all. Which finds more units is a
# question per country, not a matter of opinion -- so --probe asks both and
# prints the counts side by side, and writes nothing.
ADMIN2_DESCENT_QUERY = """
SELECT ?unit ?unitLabel ?parent ?parentLabel WHERE {
  VALUES ?country { wd:%(qid)s }
  ?country wdt:P150 ?parent .
  ?parent wdt:P150 ?unit .
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en,mul". }
}
"""


COUNTRY_QID_QUERY = """
SELECT ?country ?iso3 WHERE {
  ?country wdt:P31 wd:Q6256 ; wdt:P298 ?iso3 .
}
"""


def sparql(query: str, *, cache: bool = True, retries: int = 2) -> list[dict[str, Any]]:
    """Run a query, treating a body that will not parse as a failed fetch.

    WDQS answers 200 and streams; when the query outruns its 60-second limit
    the stream simply stops, and what arrives is valid JSON up to some byte
    and then nothing. http_get sees a 200 and caches it, so without the
    ``forget`` below every re-ask in the run is served the same broken bytes
    from disk. The byte offset is worth logging: it is the difference between
    "the endpoint refused us" and "the endpoint started answering and ran out
    of time", and only the second is worth re-asking.
    """
    url = ENDPOINT + "?" + urllib.parse.urlencode({"format": "json", "query": query})
    last: json.JSONDecodeError | None = None
    for attempt in range(retries + 1):
        payload = http_get(url, cache=cache, timeout=90,
                           headers={"Accept": "application/sparql-results+json"})
        assert isinstance(payload, str)
        try:
            data = json.loads(payload)
        except json.JSONDecodeError as exc:
            last = exc
            forget(url)
            log(f"    truncated answer: {len(payload):,} bytes, stops at "
                f"{exc.pos:,} ({attempt + 1}/{retries + 1})")
            if attempt < retries:
                time.sleep(2 ** attempt)
            continue
        return data.get("results", {}).get("bindings", [])
    raise RuntimeError(
        f"answer truncated at byte {last.pos} after {retries + 1} attempts") from last


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


def countries_in(records: list[dict[str, Any]]) -> set[str]:
    """The ISO3 codes a record set actually covers."""
    return {(row.get("country") or (row.get("id") or "")[:3]).upper()
            for row in records
            if (row.get("country") or (row.get("id") or "")[:3])}


def light_query(level: str) -> str:
    return ADMIN1_LIGHT_QUERY if level == "admin1" else ADMIN2_LIGHT_QUERY


def refuse_light_overwrite(out: Path, level: str,
                           countries: list[str] | None) -> None:
    """A light answer must never replace a full one.

    The merge replaces an answered country's records wholesale, so a light
    run over Mexico would drop the 1,877 populations the full query found
    there. Asking for every country with --light would quietly empty the
    fourteen that are already complete, which is why this refuses by name
    instead of trusting the caller to remember.
    """
    already = countries_in(read_json(out, []) or [])
    if not already:
        return
    asked = {c.upper() for c in countries} if countries else already
    clash = sorted(already & asked)
    if clash:
        raise SystemExit(
            f"--light would replace {len(clash)} country(ies) already in "
            f"{out.name} with records carrying no population, capital or "
            f"coordinates: {', '.join(clash[:20])}.\n"
            "The merge replaces an answered country wholesale, so that is a "
            "loss rather than a refresh. Run the full query for those, or "
            "leave them out of --countries.")


def probe(codes: list[str], qids: dict[str, str], sleep: float) -> None:
    """Ask each country both ways and report what each descent finds.

    Writes nothing. The point is to settle, before a 185-country sweep commits
    to one query shape, whether the cheap descent actually loses units and
    where -- rather than adopting it because it is fast and discovering the
    loss as a country-shaped hole on the map.
    """
    shapes = (("P131 + class walk", ADMIN2_LIGHT_QUERY),
              ("P150 descent", ADMIN2_DESCENT_QUERY))
    log(f"  {'':5}  {shapes[0][0]:>22}  {shapes[1][0]:>22}")
    for iso3 in codes:
        qid = qids.get(iso3)
        if not qid:
            log(f"  {iso3}:  no Wikidata country item")
            continue
        told = []
        for _, query in shapes:
            started = time.time()
            try:
                rows = sparql(query % {"qid": qid}, cache=False, retries=1)
                units = len(collapse(rows, level="admin2", iso3=iso3))
                told.append(f"{units:>6} in {time.time() - started:5.1f}s")
            except Exception as exc:
                told.append(f"{type(exc).__name__}: {str(exc)[:60]}")
            time.sleep(sleep)
        log(f"  {iso3}:  {told[0]:>22}  {told[1]:>22}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--level", default="admin1", choices=["admin1", "admin2"])
    ap.add_argument("--countries", nargs="*", help="ISO3 codes; default is every country")
    ap.add_argument("--sleep", type=float, default=1.0, help="pause between queries (be polite)")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--light", action="store_true",
                    help="ask only for units and their parents; far cheaper, "
                         "and refused for a country already in the file")
    ap.add_argument("--probe", action="store_true",
                    help="ask the named countries both ways and print what "
                         "each descent finds; writes nothing")
    ap.add_argument("--allow-shrink", action="store_true",
                    help="write even though it drops countries the existing "
                         "file covers")
    args = ap.parse_args()

    # Before any network work: a light run that would overwrite a country
    # already answered in full is refused here rather than after forty
    # minutes of queries.
    out_path = args.out or PROCESSED / f"wikidata_{args.level}.json"
    if args.light and not args.probe:
        refuse_light_overwrite(out_path, args.level, args.countries)

    # A probe writes nothing, so it needs no overwrite guard -- but it does
    # need countries, and finding that out after resolving every country QID
    # would spend a query to reject an argument.
    if args.probe and not args.countries:
        log("  --probe needs --countries: it is a comparison, not a sweep")
        return 1

    qids = country_qids()
    if args.probe:
        probe([c.upper() for c in args.countries], qids, args.sleep)
        return 0

    codes = [c.upper() for c in (args.countries or sorted(qids))]
    # Wikidata's P298 for Kosovo is XKS; geoBoundaries uses XKX. Normalise so
    # the join buckets the records with the shapes instead of beside them.
    iso3_alias = {"XKS": "XKX"}
    query = (light_query(args.level) if args.light
             else (ADMIN1_QUERY if args.level == "admin1" else ADMIN2_QUERY))

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
            # Sleep here too. The pause used to sit only on the success path,
            # so the run stopped pacing itself at exactly the moment the
            # endpoint was refusing -- and then hammered the rest of the list
            # at full speed, turning one throttled query into many.
            time.sleep(args.sleep)
            continue
        got = collapse(rows, level=args.level, iso3=iso3_alias.get(iso3, iso3))
        log(f"  {iso3}: {len(got)} {args.level} units")
        records.extend(got)
        time.sleep(args.sleep)

    # A run updates the countries it asked about and leaves the rest alone.
    #
    # This file used to be replaced wholesale by whatever the run returned,
    # which made `--countries URY` unusable: adding one country meant
    # re-querying the other thirteen in the same job, and Wikidata's endpoint
    # rate-limits and times out under load, so one 504 anywhere in the list
    # refused the whole write. Three of fourteen failed that way, and Uruguay
    # -- which had answered, with 244 units -- was thrown out with them.
    #
    # A country this run never asked about is not evidence of anything, so its
    # rows carry over untouched. A country it *did* ask about and could not
    # reach is not evidence either: the old rows stand and the failure is
    # logged. Only a query that succeeded speaks for its country.
    out = args.out or PROCESSED / f"wikidata_{args.level}.json"
    previous = read_json(out, []) or []
    answered = countries_in(records)
    kept = [row for row in previous
            if (row.get("country") or (row.get("id") or "")[:3]).upper()
            not in answered]
    merged = kept + records

    # A thinner answer is still not an answer. A Wikidata timeout looks exactly
    # like a country with no units, so the guard stays -- but it now asks the
    # sharper question the merge makes available: did a country this run
    # actually reached come back empty? A country that was asked for, answered,
    # and lost every unit is a real disappearance and worth stopping for. One
    # that simply could not be fetched is not, and no longer blocks the rest.
    #
    # The test is coverage, not row count: countries legitimately gain and lose
    # units between runs, but a country should not stop being covered at all.
    asked = {c.upper() for c in codes} - set(missing)
    before = countries_in(previous)
    lost = (before & asked) - answered
    if lost and not args.allow_shrink:
        raise SystemExit(
            f"{len(lost)} countries answered with no {args.level} units at all "
            f"but are already in {out.name}: {', '.join(sorted(lost)[:20])}.\n"
            "That is a real disappearance rather than a failed fetch, so "
            "nothing is written. Pass --allow-shrink if the units really have "
            "gone away.")
    if not records:
        raise SystemExit(
            f"every query failed ({', '.join(missing[:30])}); nothing written.")

    write_json(out, merged)
    log(f"  {len(answered)} countries refreshed, {len(before - answered)} "
        f"carried over, {len(merged)} records in {out.name}")
    if missing:
        log(f"  could not fetch {len(missing)}, previous rows kept: "
            f"{', '.join(missing[:30])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
