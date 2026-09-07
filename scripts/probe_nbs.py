#!/usr/bin/env python3
"""Whether China's statistics bureau publishes nationality by province.

China is 1.4 billion people with a population figure on every province and a
composition on four of them -- Xinjiang, Tibet, Guangxi and Ningxia -- which
are hand-curated rows in ``data/curated/admin1_seed.json`` and not an adapter.
There has never been a China adapter, and before writing one two things have to
be established, neither of them guessable from here:

* The USCB subnational series does **not** carry China. Measured, not assumed:
  ``scripts/probe_hdx.py`` lists all 34 datasets that organization publishes
  and no Chinese one is among them. The route that served Bangladesh, Myanmar,
  Colombia and eight others is closed for this country.
* So it has to be the National Bureau of Statistics, and what the NBS actually
  serves to a program is unknown. Its data portal is a JavaScript front end
  over ``easyquery.htm``, which answers JSON: ``m=getTree`` walks the indicator
  tree, ``m=QueryData`` returns figures.

The census question is 民族 (minzu), the 56 official nationalities. The Seventh
National Population Census of 2020 tabulated it by province. Whether that
tabulation is in the online database, and whether the database answers a
request from outside China at all, is what this measures.

Two failures are worth telling apart and are reported differently. A refusal --
403, a challenge page, a redirect to a portal -- is the Bureau declining to
serve this client, and getting past it by claiming to be a browser would be
circumventing a refusal rather than reading a publication; this project does
not do that. A timeout or a reset is the sandbox's egress or the distance, and
says nothing about what is published.

Read-only, and the output is the log.

Usage:
    python -m scripts.probe_nbs
    python -m scripts.probe_nbs --db fsnd --search 民族
"""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://data.stats.gov.cn/easyquery.htm"
TIMEOUT = 45

# fsnd is the provincial annual database -- the one that would carry a figure
# per province. hgnd is national annual, and a national-only table cannot fill
# thirty-three provinces however good it is.
DATABASES = {
    "fsnd": "provincial, annual",
    "hgnd": "national, annual",
    "csnd": "cities, annual",
}

# 民族 is nationality/minzu; 人口 is population, included as a control -- if the
# tree comes back and holds population but not minzu, that is a real answer
# about what is published, and if it holds neither the walk itself is wrong.
TERMS = ("民族", "人口", "少数民族")


def get(**params: object) -> tuple[str, object]:
    """One easyquery call. Returns (status, parsed-or-raw)."""
    url = f"{BASE}?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={
        # This project's own name. Not a browser string: the point is to be
        # identifiable, and a refusal aimed at automated clients is a finding
        # to record rather than a lock to pick.
        "User-Agent": "DemographicMap/1.0 (+https://github.com/advaitsridhar/DemographicMap)",
        "Accept": "application/json, text/plain, */*",
    })
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            body = response.read()
            status = f"HTTP {response.status}"
    except urllib.error.HTTPError as err:
        return f"HTTP {err.code} {err.reason or ''}".strip(), None
    except Exception as err:                        # noqa: BLE001 -- reported
        return f"{type(err).__name__}: {err}", None
    try:
        return status, json.loads(body)
    except ValueError:
        text = body.decode("utf-8", "replace")
        return f"{status}, not JSON ({len(body)} bytes)", text[:400]


def walk(node: object, depth: int = 0, out: list | None = None) -> list:
    """Every node of an indicator tree, flattened."""
    out = [] if out is None else out
    if isinstance(node, list):
        for item in node:
            walk(item, depth, out)
    elif isinstance(node, dict):
        out.append((depth, str(node.get("id", "")), str(node.get("name", "")),
                    bool(node.get("isParent"))))
        for key in ("children", "nodes"):
            if node.get(key):
                walk(node[key], depth + 1, out)
    return out


def probe(db: str, terms: tuple[str, ...]) -> None:
    print(f"\n=== {db} ({DATABASES.get(db, 'unknown')}) ===")
    status, payload = get(m="getTree", dbcode=db, wdcode="zb", treeId="zb")
    print(f"    getTree: {status}")
    if payload is None:
        print("    no body -- nothing can be said about what this database holds")
        return
    if isinstance(payload, str):
        print(f"    body was not JSON, which usually means a portal or a "
              f"challenge page rather than the API:\n      {payload[:300]}")
        return
    nodes = walk(payload)
    print(f"    {len(nodes)} top-level indicator(s)")
    for _, node_id, name, is_parent in nodes[:40]:
        print(f"      {node_id:<12} {'+' if is_parent else ' '} {name}")
    for term in terms:
        hits = [n for n in nodes if term in n[2]]
        print(f"    '{term}': {len(hits)} matching indicator(s)")
        for _, node_id, name, _ in hits[:10]:
            print(f"      {node_id:<12} {name}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default="fsnd,hgnd",
                    help="comma-separated: " + ", ".join(DATABASES))
    ap.add_argument("--search", default=",".join(TERMS))
    args = ap.parse_args(argv)

    terms = tuple(t.strip() for t in args.search.split(",") if t.strip())
    for db in (d.strip() for d in args.db.split(",") if d.strip()):
        probe(db, terms)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
