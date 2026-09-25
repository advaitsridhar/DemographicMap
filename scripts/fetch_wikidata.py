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
    python scripts/fetch_wikidata.py --level admin2 --hydrate [--countries ROU]
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


# Population and coordinates for units already identified, looked up by id.
#
# The --light and descent sweeps of 21-22 September 2026 found 75,232
# second-level items and fetched none of their populations, because the query
# that walks the class tree could not carry the OPTIONAL blocks inside WDQS's
# 60-second limit. 68,764 rows came back "No P1082 statement", among them
# every one of Romania's 3,186 communes -- which do have one. Asking for known
# items by id is a different and cheap query: no walk, just a lookup.
#
# A statement that applies to part of the unit (P518, e.g. its urban area) is
# not the unit's population and is left out; a deprecated one is wrong by the
# item's own account. Among the rest the preferred rank wins where there is
# one, and then the latest year.
HYDRATE_QUERY = """
SELECT ?unit ?pop ?popTime ?rank ?coord WHERE {
  VALUES ?unit { %(ids)s }
  OPTIONAL { ?unit p:P1082 ?popSt .
             ?popSt ps:P1082 ?pop ; wikibase:rank ?rank .
             FILTER NOT EXISTS { ?popSt pq:P518 ?part . }
             OPTIONAL { ?popSt pq:P585 ?popTime . } }
  OPTIONAL { ?unit wdt:P625 ?coord . }
}
"""
HYDRATE_BATCH = 100

COUNTRY_QID_QUERY = """
SELECT ?country ?iso3 WHERE {
  ?country wdt:P31 wd:Q6256 ; wdt:P298 ?iso3 .
}
"""


def sparql(query: str, *, cache: bool = True, retries: int = 1) -> list[dict[str, Any]]:
    """Run a query, treating a body that will not parse as a failed fetch.

    WDQS answers 200 and streams, and when the query outruns its 60-second
    limit it abandons the stream and appends its own error to what it has
    already sent. The body is then valid JSON up to some byte followed by
    something that is not JSON at all -- Austria's was 1,250,094 bytes ending
    at 1,244,867, Australia's 18,445,340 ending at 18,440,112, the same 5,227
    trailing bytes in both.

    http_get sees a 200 and caches it, so without the ``forget`` below every
    re-ask in the run is served the same broken bytes from disk.

    Re-asking barely helps and the default is one attempt, not four: the
    failure is a property of the query, and both of Austria's attempts
    returned byte-identical bodies for 90 seconds each. What answers such a
    country is a cheaper query, which is ADMIN2_DESCENT_QUERY's job.
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
            tail = " ".join(payload[exc.pos:].split())[:200]
            log(f"    answer unparseable: {len(payload):,} bytes, JSON ends at "
                f"{exc.pos:,}, then {len(payload) - exc.pos:,} more "
                f"({attempt + 1}/{retries + 1})")
            log(f"    what follows it: {tail!r}")
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


# Where two items share an ISO3 and the query's answer is the wrong one: the
# Kingdom of the Netherlands and the Kingdom of Denmark both carry P298, and
# their subdivisions are tagged with the constituent country. Asked under the
# kingdom, the Netherlands' 344 municipalities met 38 rows.
COUNTRY_QID_OVERRIDE = {"NLD": "Q55", "DNK": "Q35"}


def country_qids() -> dict[str, str]:
    cached = read_json(RAW / "codes" / "wikidata_countries.json", None)
    if cached:
        return {**cached, **COUNTRY_QID_OVERRIDE}
    rows = sparql(COUNTRY_QID_QUERY)
    out = {value(r, "iso3"): value(r, "country") for r in rows if value(r, "iso3")}
    write_json(RAW / "codes" / "wikidata_countries.json", out)
    return {**out, **COUNTRY_QID_OVERRIDE}


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


def union_by_unit(primary: list[dict[str, Any]],
                  secondary: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Add the units the primary query missed, keeping the primary's rows.

    Order matters: a unit found both ways is kept as the primary found it,
    because the full query carries a population, a capital and coordinates
    and the descent carries none of them. The descent only ever adds units,
    never replaces one.
    """
    seen = {row["unit"]["value"] for row in primary if row.get("unit")}
    return primary + [row for row in secondary
                      if row.get("unit") and row["unit"]["value"] not in seen]


def admin2_rows(qid: str, primary: str, sleep: float) -> tuple[list[dict[str, Any]], str]:
    """Ask both ways and return the union, and a word on what answered.

    Neither descent covers a country on its own, which the probe of 22
    September 2026 measured over eight of them:

        AFG   494 in 10.5s     404 in  0.4s
        AUT   truncated        116 in  0.3s
        AZE   191 in 34.8s       0 in  0.2s
        AUS   truncated (18MB) 581 in  1.4s
        AGO   428 in 12.4s     164 in  0.3s
        BGR   306 in 16.4s     266 in  0.4s
        BIH   134 in 30.4s      68 in  0.2s
        BEL    30 in 20.8s      11 in  0.3s

    P131 with the class walk is the better answer nearly everywhere and the
    descent loses more than half of Angola, Belgium and Bosnia and the whole
    of Azerbaijan -- so it cannot replace it. But it costs under a second and
    it answers the two countries P131 cannot answer at all. So both are asked.

    A country whose P131 query fails is served by the descent alone, and this
    returns "descent only" so the caller can say which countries those are.
    A country that is short is a gap; a country that is short and does not
    say so is the error this project treats as worse.
    """
    try:
        # retries=0: a truncation is a property of the query, not the moment,
        # and there is a fallback below. This only governs re-parsing -- a
        # genuine network error is still retried inside http_get.
        rows = sparql(primary % {"qid": qid}, retries=0)
    except Exception as exc:
        log(f"    primary query failed ({str(exc)[:80]}); falling back")
        rows, reached = [], "descent only"
    else:
        reached = "both"
    time.sleep(sleep)
    try:
        descent = sparql(ADMIN2_DESCENT_QUERY % {"qid": qid})
    except Exception as exc:
        if reached == "descent only":
            raise
        log(f"    descent failed ({str(exc)[:80]})")
        return rows, "primary only"
    united = union_by_unit(rows, descent)
    if reached == "descent only":
        return united, reached
    return united, f"{len(united) - len(rows)} added by descent"


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


def best_statement(rows: list[dict[str, Any]]) -> tuple[int, int | None] | None:
    """The population a unit's statements settle on: (count, year), or None."""
    found: list[tuple[bool, int, int, int | None]] = []
    for row in rows:
        rank = (value(row, "rank") or "").rsplit("#", 1)[-1]
        if rank == "DeprecatedRank" or value(row, "pop") is None:
            continue
        try:
            pop = int(float(value(row, "pop")))
        except ValueError:
            continue
        if pop <= 0:
            continue
        year = (value(row, "popTime") or "")[:4]
        year_i = int(year) if year.isdigit() else None
        found.append((rank == "PreferredRank", year_i or 0, pop, year_i))
    if not found:
        return None
    # Preferred first, then the latest year; a tie on both keeps the larger
    # count only so the answer does not depend on the order WDQS streams in.
    best = max(found)
    return best[2], best[3]


ASKED_BY_ID = "No P1082 statement on Wikidata (asked by id)."


# Names in the languages a boundary file may write a unit in. geoBoundaries
# spells Latvia's parishes "Abavas pag.", Estonia's rural municipalities "Abja
# vald" and Tunisia's delegations in Arabic, where Wikidata's English label is
# "Abava Parish", "Abja Rural Municipality" or a romanisation. The build will
# not strip a local generic word to make them meet -- "Ventspils" and
# "Ventspils novads" are two places -- so the item's own local label is asked
# for instead and carried as an alias. English alternative labels come too:
# they hold the other romanisations ("Ad Dahi" beside "Ad Dohi").
LOCAL_LANGUAGES: dict[str, tuple[str, ...]] = {
    "AFG": ("ps", "fa"), "ARG": ("es",), "AZE": ("az",), "BLR": ("be", "ru"),
    "CHE": ("de", "fr", "it"), "CHL": ("es",), "CYP": ("el", "tr"),
    "EGY": ("ar",), "EST": ("et",), "FIN": ("fi", "sv"), "HTI": ("fr", "ht"),
    "IRN": ("fa",), "IRQ": ("ar", "ku"), "JOR": ("ar",), "KEN": ("sw",),
    "KHM": ("km",), "LSO": ("st",), "LTU": ("lt",), "LVA": ("lv",),
    "MKD": ("mk",), "NOR": ("nb", "nn", "no"), "ROU": ("ro",), "RUS": ("ru",),
    "SLV": ("es",), "SOM": ("so",), "SVK": ("sk",), "SVN": ("sl",),
    "SYR": ("ar",), "TUN": ("ar", "fr"), "UKR": ("uk", "ru"), "UZB": ("uz",),
    "VNM": ("vi",), "YEM": ("ar",),
}

LABELS_QUERY = """
SELECT ?unit ?label WHERE {
  VALUES ?unit { %(ids)s }
  { ?unit rdfs:label ?label . } UNION { ?unit skos:altLabel ?label . }
  FILTER(LANG(?label) IN (%(langs)s))
}
"""


def joined_items(level: str) -> set[str]:
    """Every Wikidata item the built site has joined to a unit."""
    out: set[str] = set()
    for shard in sorted((PROCESSED.parent.parent / "site" / "data" / level).glob("*.json")):
        for entity in read_json(shard, []) or []:
            if entity.get("wikidata"):
                out.add(entity["wikidata"])
    return out


def enrich(path: Path, countries: list[str] | None, sleep: float,
           budget_minutes: float = 38.0, level: str = "admin2") -> int:
    """Local-language names, and populations, for rows that joined no unit.

    Only rows in a country LOCAL_LANGUAGES names, and only rows no unit has
    taken: a row already joined needs no second name. The names go to
    ``aliases``; a population found goes where hydrate would put it, since a
    row that starts to match should arrive with its figure.
    """
    records = read_json(path, []) or []
    wanted = {c.upper() for c in countries} if countries else set(LOCAL_LANGUAGES)
    joined = joined_items(level)
    todo: dict[str, list[dict[str, Any]]] = {}
    for rec in records:
        iso3 = (rec.get("country") or "").upper()
        if iso3 in wanted and iso3 in LOCAL_LANGUAGES and rec.get("wikidata") \
                and rec["wikidata"] not in joined:
            todo.setdefault(iso3, []).append(rec)
    log(f"  {sum(len(v) for v in todo.values()):,} unjoined rows in "
        f"{len(todo)} countries")
    deadline = time.time() + budget_minutes * 60
    named = 0
    for iso3, recs in sorted(todo.items()):
        if time.time() > deadline:
            log(f"  stopped at the budget before {iso3}; run again to go on")
            break
        langs = ", ".join(f'"{lang}"' for lang in ("en",) + LOCAL_LANGUAGES[iso3])
        by_qid: dict[str, list[dict[str, Any]]] = {}
        for rec in recs:
            by_qid.setdefault(rec["wikidata"], []).append(rec)
        qids = sorted(by_qid)
        for start in range(0, len(qids), HYDRATE_BATCH):
            batch = qids[start:start + HYDRATE_BATCH]
            try:
                rows = sparql(LABELS_QUERY % {
                    "ids": " ".join(f"wd:{q}" for q in batch), "langs": langs},
                    cache=False, retries=2)
            except Exception as exc:
                log(f"    {iso3} labels batch failed: {str(exc)[:80]}")
                time.sleep(sleep * 4)
                continue
            for row in rows:
                label = " ".join((value(row, "label") or "").split())
                for rec in by_qid.get(value(row, "unit"), []):
                    known = rec.setdefault("aliases", [])
                    if label and label != rec.get("name") and label not in known:
                        known.append(label)
                        named += 1
            time.sleep(sleep)
        log(f"  {iso3}: names for {len(qids):,} items")
    write_json(path, records)
    log(f"  {named:,} local and alternative names added")
    # Their populations, by the same lookup hydrate uses.
    return hydrate(path, list(todo), sleep,
                   max(1.0, (deadline - time.time()) / 60), level,
                   qids={rec["wikidata"] for recs in todo.values() for rec in recs})


# Every item of one class in one country, with what hydrate fetches. For a
# country the structural walk under-reached: the Netherlands' 344 drawn
# municipalities met 38 rows, because its provinces' P150 lists are partial
# and the P131 walk timed out. A class is a flat lookup and cheap.
CLASS_QUERY = """
SELECT ?unit ?unitLabel ?parent ?parentLabel ?pop ?popTime ?rank ?coord WHERE {
  ?unit wdt:P31 wd:%(cls)s ; wdt:P17 wd:%(country)s .
  OPTIONAL { ?unit wdt:P131 ?parent . }
  OPTIONAL { ?unit p:P1082 ?popSt .
             ?popSt ps:P1082 ?pop ; wikibase:rank ?rank .
             FILTER NOT EXISTS { ?popSt pq:P518 ?part . }
             OPTIONAL { ?popSt pq:P585 ?popTime . } }
  OPTIONAL { ?unit wdt:P625 ?coord . }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en,mul". }
}
"""


def class_sweep(path: Path, specs: list[str], level: str = "admin2") -> int:
    """Add the items of a class the file lacks, and populations it lacks.

    ``specs`` are ISO3:QCLASS. A row already in the file keeps everything it
    has; a population is only ever added where the row has none.
    """
    records = read_json(path, []) or []
    by_qid = {r.get("wikidata"): r for r in records if r.get("wikidata")}
    qids = country_qids()
    added = filled = 0
    for spec in specs:
        iso3, cls = spec.split(":", 1)
        country = qids.get(iso3.upper())
        if not country:
            log(f"  {iso3}: no Wikidata country item")
            continue
        rows = sparql(CLASS_QUERY % {"cls": cls, "country": country},
                      cache=False, retries=2)
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            grouped.setdefault(value(row, "unit"), []).append(row)
        found = 0
        for qid, group in grouped.items():
            name = value(group[0], "unitLabel")
            if not qid or not name or name == qid:
                continue
            found += 1
            best = best_statement(group)
            point = next((parse_point(value(r, "coord")) for r in group
                          if value(r, "coord")), None)
            rec = by_qid.get(qid)
            if rec is None:
                parent = next((r for r in group if value(r, "parent")), {})
                rec = {
                    "id": f"{iso3.upper()}-WD-{qid}", "wikidata": qid, "level": level,
                    "name": name, "parent": value(parent, "parent") or iso3.upper(),
                    "parent_name": value(parent, "parentLabel"),
                    "country": iso3.upper(), "capital": gap(NOT_AVAILABLE),
                    "coordinates": point or gap(NOT_AVAILABLE),
                    "inception": gap(NOT_AVAILABLE), "iso_3166_2": gap(NOT_AVAILABLE),
                    "population": (measure(best[0], year=best[1], source="Wikidata (CC0)")
                                   if best else gap(NOT_AVAILABLE, ASKED_BY_ID)),
                    "sources": [{"field": "population/capital/coordinates",
                                 "name": "Wikidata",
                                 "url": f"https://www.wikidata.org/wiki/{qid}",
                                 "license": "CC0"}],
                }
                records.append(rec)
                by_qid[qid] = rec
                added += 1
                filled += bool(best)
            elif best and not (isinstance(rec.get("population"), dict)
                               and rec["population"].get("value")):
                rec["population"] = measure(best[0], year=best[1], source="Wikidata (CC0)")
                filled += 1
        log(f"  {iso3} {cls}: {found} items of the class")
    write_json(path, records)
    log(f"  {added} rows added, {filled} populations filled")
    return 0


CLASSES_OF_QUERY = """
SELECT ?class ?classLabel (COUNT(DISTINCT ?item) AS ?n) WHERE {
  VALUES ?name { %(names)s }
  ?item rdfs:label ?name ; wdt:P17 wd:%(country)s ; wdt:P31 ?class .
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en,mul". }
} GROUP BY ?class ?classLabel ORDER BY DESC(?n) LIMIT 15
"""


CHILD_CLASSES_QUERY = """
SELECT ?class ?classLabel (COUNT(DISTINCT ?item) AS ?n) WHERE {
  VALUES ?parent { %(parents)s }
  ?item wdt:P131 ?parent ; wdt:P31 ?class .
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en,mul". }
} GROUP BY ?class ?classLabel ORDER BY DESC(?n) LIMIT 20
"""


def child_classes(codes: list[str]) -> int:
    """The classes of the items inside a country's first-order Wikidata units.

    Where the map's second level is a finer layer than the items the sweep
    found -- China's 2,370 counties against its 474 prefectures -- the
    classes to sweep are the classes of those items' children, and this
    asks for them rather than guessing ids. Writes nothing.
    """
    for level in ("admin1", "admin2"):
        records = read_json(PROCESSED / f"wikidata_{level}.json", []) or []
        records = records["records"] if isinstance(records, dict) else records
        for iso3 in codes:
            qids = sorted({r["wikidata"] for r in records
                           if r.get("country") == iso3.upper() and r.get("wikidata")})
            if not qids:
                continue
            rows = []
            for i in range(0, len(qids), 150):
                rows += sparql(CHILD_CLASSES_QUERY % {
                    "parents": " ".join(f"wd:{q}" for q in qids[i:i + 150])}, cache=False)
            counts: dict[tuple[str, str], int] = {}
            for row in rows:
                key = (value(row, "class") or "", value(row, "classLabel") or "")
                counts[key] = counts.get(key, 0) + int(value(row, "n") or 0)
            log(f"== {iso3} children of {len(qids)} {level} items")
            for (cls, label), n in sorted(counts.items(), key=lambda kv: -kv[1])[:20]:
                log(f"  {cls:12} {n:6}  {label}")
    return 0


def probe_classes(codes: list[str], level: str = "admin2") -> int:
    """Which classes the items named like a country's blank units belong to.

    Takes up to 60 names of the units the built site shows no population for
    and asks which classes the country's items of exactly those English names
    are instances of. Writes nothing; it is how a --class-sweep is chosen.
    """
    qids = country_qids()
    site = PROCESSED.parent.parent / "site" / "data" / level
    for iso3 in codes:
        names = []
        for entity in read_json(site / f"{iso3.upper()}.json", []) or []:
            pop = entity.get("population")
            if not (isinstance(pop, dict) and pop.get("value")) and not entity.get("water"):
                name = (entity.get("name") or "").replace('"', "")
                if name and not name[0].isdigit():
                    names.append(name)
        names = names[:60]
        rows = sparql(CLASSES_OF_QUERY % {
            "names": " ".join(f'"{n}"@en' for n in names),
            "country": qids.get(iso3.upper(), "Q0")}, cache=False, retries=2)
        log(f"  {iso3}: {len(names)} blank names asked")
        for row in rows:
            log(f"    {value(row, 'class')}  {value(row, 'n'):>4}  {value(row, 'classLabel')}")
    return 0


def blank_items(level: str) -> set[str]:
    """The Wikidata items joined to a unit the built site shows no population for."""
    out: set[str] = set()
    for shard in sorted((PROCESSED.parent.parent / "site" / "data" / level).glob("*.json")):
        for entity in read_json(shard, []) or []:
            pop = entity.get("population")
            if entity.get("wikidata") and not entity.get("water") \
                    and not isinstance(pop, (int, float)) \
                    and not (isinstance(pop, dict) and pop.get("value")):
                out.add(entity["wikidata"])
    return out


def hydrate(path: Path, countries: list[str] | None, sleep: float,
            budget_minutes: float = 38.0, level: str = "admin2",
            qids: set[str] | None = None) -> int:
    """Fill population and coordinates for rows that have neither, by id.

    Only ever fills: a row that already carries a population keeps it, and
    one Wikidata still has nothing for keeps its gap. Nothing else about a
    row changes, so the join the build made on names is the same join.
    """
    records = read_json(path, []) or []
    wanted = {c.upper() for c in countries} if countries else None
    # Only the items a blank unit on the map is waiting for. Of 68,764 rows
    # without a population, about 12,450 are joined to a unit that has none;
    # the rest sit on units another source already fills, or join nothing.
    # A run on 24 September 2026 asking for all of them reached 6,150 in the
    # job's 45 minutes, against a WDQS answering 502 and timing out.
    waiting = qids if qids is not None else blank_items(level)
    todo = [r for r in records
            if r.get("wikidata") in waiting
            and (wanted is None or (r.get("country") or "").upper() in wanted)
            and not (isinstance(r.get("population"), dict)
                     and (r["population"].get("value")
                          or r["population"].get("note") == ASKED_BY_ID))]
    log(f"  {len(todo):,} rows without a population"
        + (f" in {', '.join(sorted(wanted))}" if wanted else ""))
    by_qid: dict[str, list[dict[str, Any]]] = {}
    for rec in todo:
        by_qid.setdefault(rec["wikidata"], []).append(rec)
    ordered = sorted(by_qid)
    filled = placed = failed = 0
    # The job is cancelled at 45 minutes and a cancelled job commits nothing
    # it had not saved, so the run stops itself short of that and says where.
    deadline = time.time() + budget_minutes * 60
    for start in range(0, len(ordered), HYDRATE_BATCH):
        if time.time() > deadline:
            log(f"  stopped at the {budget_minutes:.0f}-minute budget with "
                f"{len(ordered) - start:,} items unasked; run again to go on")
            break
        batch = ordered[start:start + HYDRATE_BATCH]
        try:
            rows = sparql(HYDRATE_QUERY % {"ids": " ".join(f"wd:{q}" for q in batch)},
                          cache=False, retries=2)
        except Exception as exc:
            failed += len(batch)
            log(f"    batch {start // HYDRATE_BATCH + 1} failed: {str(exc)[:80]}")
            time.sleep(sleep * 4)
            continue
        grouped: dict[str, list[dict[str, Any]]] = {}
        coords: dict[str, list[float]] = {}
        for row in rows:
            qid = value(row, "unit")
            grouped.setdefault(qid, []).append(row)
            point = parse_point(value(row, "coord"))
            if point and qid not in coords:
                coords[qid] = point
        for qid in batch:
            best = best_statement(grouped.get(qid, []))
            for rec in by_qid[qid]:
                if best:
                    rec["population"] = measure(best[0], year=best[1],
                                                source="Wikidata (CC0)")
                    filled += 1
                else:
                    rec["population"] = gap(NOT_AVAILABLE, ASKED_BY_ID)
                if qid in coords and not isinstance(rec.get("coordinates"), list):
                    rec["coordinates"] = coords[qid]
                    placed += 1
        if (start // HYDRATE_BATCH) % 20 == 0:
            log(f"    {min(start + HYDRATE_BATCH, len(ordered)):,} of {len(ordered):,} "
                f"items asked; {filled:,} populations so far")
        # Saved as it goes: the job has a 45-minute limit, and a run cut off
        # at minute 44 used to keep nothing of what it had found.
        if (start // HYDRATE_BATCH) % 40 == 39:
            write_json(path, records)
        time.sleep(sleep)
    write_json(path, records)
    log(f"  filled {filled:,} populations and {placed:,} coordinates; "
        f"{failed:,} items in failed batches keep their gaps")
    return 0


ITEM_CLASSES_QUERY = """
SELECT ?item ?class ?classLabel WHERE {
  VALUES ?item { %(ids)s }
  ?item wdt:P31 ?class .
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en,mul". }
}
"""
ITEM_CLASSES_BATCH = 200


def item_classes(path: Path, level: str, sleep: float,
                 budget_minutes: float = 38.0) -> int:
    """What each item that gives this level a population is an instance of.

    A name join can reach the town of a district's name rather than the
    district, and the figure it brings looks like any other. The build reads
    this file to tell the two apart: an item that is only ever a village, a
    town or a city is not a second-level unit, whatever it is called.
    Resumes from the file, so a run cut short by the budget goes on.
    """
    items: set[str] = set()
    for name in (f"wikidata_{level}.json", f"wikidata_{level}_classes.json"):
        for rec in read_json(PROCESSED / name, []) or []:
            pop = rec.get("population")
            if rec.get("wikidata") and isinstance(pop, dict) and pop.get("value"):
                items.add(rec["wikidata"])
    known: dict[str, list[list[str]]] = read_json(path, {}) or {}
    ordered = sorted(items - set(known))
    log(f"  {len(items):,} items give a {level} population; "
        f"{len(ordered):,} not yet asked")
    deadline = time.time() + budget_minutes * 60
    failed = 0
    for start in range(0, len(ordered), ITEM_CLASSES_BATCH):
        if time.time() > deadline:
            log(f"  stopped at the {budget_minutes:.0f}-minute budget with "
                f"{len(ordered) - start:,} items unasked; run again to go on")
            break
        batch = ordered[start:start + ITEM_CLASSES_BATCH]
        try:
            rows = sparql(ITEM_CLASSES_QUERY % {"ids": " ".join(f"wd:{q}" for q in batch)},
                          cache=False, retries=2)
        except Exception as exc:
            failed += len(batch)
            log(f"    batch {start // ITEM_CLASSES_BATCH + 1} failed: {str(exc)[:80]}")
            time.sleep(sleep * 4)
            continue
        found: dict[str, list[list[str]]] = {q: [] for q in batch}
        for row in rows:
            found.setdefault(value(row, "item"), []).append(
                [value(row, "class"), value(row, "classLabel")])
        known.update({q: sorted(c) for q, c in found.items()})
        if (start // ITEM_CLASSES_BATCH) % 20 == 19:
            write_json(path, dict(sorted(known.items())))
        time.sleep(sleep)
    write_json(path, dict(sorted(known.items())))
    log(f"  {len(known):,} items' classes on file; {failed:,} in failed batches")
    return 0


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
    ap.add_argument("--budget", type=float, default=38.0,
                    help="--hydrate stops and saves after this many minutes")
    ap.add_argument("--child-classes", nargs="*", default=None,
                    help="ISO3 codes: list the classes of the items inside each country's "
                         "known first- and second-order items; writes nothing")
    ap.add_argument("--probe-classes", nargs="*", default=None,
                    help="ISO3s; which classes items named like their blank units are")
    ap.add_argument("--class-sweep", nargs="*", default=None,
                    help="ISO3:QCLASS pairs; every item of the class in the country")
    ap.add_argument("--enrich", action="store_true",
                    help="local-language names and populations for rows no "
                         "unit has joined, in the countries LOCAL_LANGUAGES names")
    ap.add_argument("--hydrate", action="store_true",
                    help="fill population and coordinates for rows already in "
                         "the file that lack them, looked up by id")
    ap.add_argument("--qids", nargs="*", default=None,
                    help="with --hydrate: ask for these items rather than the "
                         "ones the built site shows blank")
    ap.add_argument("--item-classes", action="store_true",
                    help="record what every item giving the level a population "
                         "is an instance of, for the build's town check")
    args = ap.parse_args()
    if args.item_classes:
        return item_classes(args.out or PROCESSED / f"wikidata_{args.level}_item_classes.json",
                            args.level, args.sleep, args.budget)
    if args.child_classes:
        return child_classes(args.child_classes)
    if args.probe_classes:
        return probe_classes(args.probe_classes, args.level)
    if args.class_sweep:
        return class_sweep(args.out or PROCESSED / f"wikidata_{args.level}.json",
                           args.class_sweep, args.level)
    if args.enrich:
        return enrich(args.out or PROCESSED / f"wikidata_{args.level}.json",
                      args.countries, args.sleep, args.budget, args.level)
    if args.hydrate:
        return hydrate(args.out or PROCESSED / f"wikidata_{args.level}.json",
                       args.countries, args.sleep, args.budget, args.level,
                       qids=set(args.qids) if args.qids else None)

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
            if args.level == "admin2":
                rows, reached = admin2_rows(qid, query, args.sleep)
            else:
                rows, reached = sparql(query % {"qid": qid}), ""
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
        log(f"  {iso3}: {len(got)} {args.level} units"
            + (f" ({reached})" if reached else ""))
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
