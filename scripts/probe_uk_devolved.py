#!/usr/bin/env python3
"""What Scotland and Northern Ireland serve, and in what shape.

Reading the UK census at Nomis' county tier took its second-order coverage from
152 shapes to 171. The 45 that remain are all Scottish council areas and
Northern Irish districts, and they are not a join failure: the ONS census
covers **England and Wales**. Scotland ran its own in 2022 through National
Records of Scotland and Northern Ireland in 2021 through NISRA, so filling
those 45 means two more offices.

Neither speaks the protocol this project already has an adapter for. Most of
Europe's offices run PxWeb and ``fetch_census/pxweb.py`` makes each a config
entry; NISRA runs **PxStat**, whose API is JSON-RPC with a JSON-stat read
endpoint, and Scotland publishes through a **linked-data** platform answering
SPARQL. So the question is not which table but whether either can be read at
all, and in what format, before an adapter is shaped around a guess.

Both offices publish the two fields this map wants. NISRA's Census 2021 has
MS-B01 religion and MS-B02 ethnic group by the 11 local government districts;
Scotland's Census 2022 has ethnicity and religion by the 32 council areas.
Whether a program can fetch them is the measurement.

Read-only, and the output is the log.

Usage:
    python -m scripts.probe_uk_devolved
"""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.parse
import urllib.request

TIMEOUT = 60
UA = "DemographicMap/1.0 (+https://github.com/advaitsridhar/DemographicMap)"

# Concrete candidates rather than a crawl. Each is a documented entry point for
# one office, and what matters is the status and the first bytes of the body:
# a portal or a challenge page answers 200 with HTML, which is a different
# finding from an API answering JSON.
CANDIDATES: tuple[tuple[str, str, str], ...] = (
    ("NIR", "PxStat dataset list (JSON-RPC)",
     "https://ws.nisra.gov.uk/public/api.jsonrpc?data="
     + urllib.parse.quote(json.dumps({
         "jsonrpc": "2.0", "method": "PxStat.Data.Cube_API.ReadCollection",
         "params": {"language": "en", "format": {"type": "JSON-stat",
                                                 "version": "2.0"}}, "id": 1}))),
    ("NIR", "PxStat read MS-B01 (religion) as JSON-stat",
     "https://ws.nisra.gov.uk/public/api.restful/PxStat.Data.Cube_API."
     "ReadDataset/MS-B01/JSON-stat/2.0/en"),
    ("NIR", "PxStat read MS-B02 (ethnic group) as JSON-stat",
     "https://ws.nisra.gov.uk/public/api.restful/PxStat.Data.Cube_API."
     "ReadDataset/MS-B02/JSON-stat/2.0/en"),
    ("SCO", "statistics.gov.scot SPARQL, ask for the graphs",
     "https://statistics.gov.scot/sparql.json?query="
     + urllib.parse.quote("SELECT DISTINCT ?g WHERE { GRAPH ?g {?s ?p ?o} } LIMIT 25")),
    ("SCO", "Scotland's Census front door",
     "https://www.scotlandscensus.gov.uk/"),
    ("SCO", "NRS open data portal",
     "https://www.nrscotland.gov.uk/statistics-and-data/statistics/"),
)


def probe(who: str, what: str, url: str) -> None:
    print(f"\n=== {who}: {what} ===")
    print(f"    {url[:150]}{'...' if len(url) > 150 else ''}")
    request = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept": "application/json, text/plain, */*"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            body = response.read()
            status, ctype = response.status, response.headers.get("Content-Type", "")
    except urllib.error.HTTPError as err:
        print(f"    HTTP {err.code} {err.reason or ''}".rstrip())
        return
    except Exception as err:                        # noqa: BLE001 -- reported
        print(f"    {type(err).__name__}: {err}")
        return
    print(f"    HTTP {status} | {ctype} | {len(body)} bytes")
    text = body.decode("utf-8", "replace")
    if "json" in ctype.lower() or text.lstrip()[:1] in "{[":
        try:
            payload = json.loads(text)
        except ValueError:
            print(f"    declared JSON and did not parse: {text[:200]}")
            return
        # JSON-stat names its dimensions, and the dimension names are the whole
        # question: a table cut by council area is usable and one cut by
        # Scotland alone is not.
        if isinstance(payload, dict):
            keys = [k for k in payload if not k.startswith("@")]
            print(f"    JSON keys: {keys[:10]}")
            for holder in ("dimension", "id", "size", "label"):
                if holder in payload:
                    print(f"      {holder}: {str(payload[holder])[:220]}")
            res = payload.get("result")
            if isinstance(res, dict):
                print(f"      result keys: {list(res)[:10]}")
                if "link" in res:
                    items = (res.get("link") or {}).get("item") or {}
                    print(f"      datasets listed: {len(items)}")
                    for name in list(items)[:12]:
                        print(f"        {name}")
        else:
            print(f"    JSON array of {len(payload)}")
        return
    head = " ".join(text[:400].split())
    print(f"    not JSON: {head[:300]}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", default="", help="NIR or SCO")
    args = ap.parse_args(argv)
    for who, what, url in CANDIDATES:
        if args.only and who != args.only.upper():
            continue
        probe(who, what, url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
