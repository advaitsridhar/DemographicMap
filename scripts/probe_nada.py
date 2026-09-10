#!/usr/bin/env python3
"""Search a NADA microdata catalogue for surveys that ask the four fields.

NADA is the World Bank's National Data Archive software, and dozens of
statistical offices run it -- Nigeria's is microdata.nigerianstat.gov.ng. Like
PxWeb, one shape serves many countries, so this is written against the software
rather than against one office.

What makes it worth asking is the *variable* endpoint. A catalogue entry says a
survey exists; the variable list says whether it asked about religion, ethnicity
or language, which is the question that decides whether a country can be filled
here. Nigeria matters because the two routes already measured both failed on
shape rather than availability: the Census Bureau's workbook carries only
citizenship, and DHS's subnational series carries indicators broken down *by*
region rather than the distribution of any characteristic.

Two cautions this prints rather than hides. A NADA catalogue commonly lists
microdata that needs registration to download, so "listed" is not "fetchable";
and a survey is a sample with a stated universe, not a census count, which this
project may use but must label.

Read-only. The output is the log.

Usage:
    python scripts/probe_nada.py --base https://microdata.nigerianstat.gov.ng
    python scripts/probe_nada.py --base URL --study 63
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

TIMEOUT = 60
# What a composition question is called, across the wordings offices use.
WANTED = ("religion", "ethnic", "tribe", "language", "mother tongue",
          "dialect", "denomination", "faith")


def get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def studies(base: str, keyword: str, limit: int) -> list[dict]:
    url = f"{base.rstrip('/')}/index.php/api/catalog/search?" + \
        urllib.parse.urlencode({"sk": keyword, "ps": limit})
    print(f"\n=== NADA search: {keyword!r} at {base} ===")
    try:
        payload = get(url)
    except Exception as err:                        # noqa: BLE001 -- reported
        print(f"    {type(err).__name__}: {err}")
        return []
    result = payload.get("result") or payload
    rows = result.get("rows") or result.get("study") or []
    print(f"    {result.get('found', len(rows))} study/studies, showing {len(rows)}")
    for row in rows:
        print(f"    id={str(row.get('id','?')):<6} {str(row.get('year_end') or row.get('year_start') or '?'):<6} "
              f"{str(row.get('title',''))[:90]}")
    return rows


def variables(base: str, study: str) -> None:
    """The variable list, which is what says whether a question was asked."""
    url = f"{base.rstrip('/')}/index.php/api/catalog/{study}/variables"
    print(f"\n=== NADA variables: study {study} ===")
    try:
        payload = get(url)
    except Exception as err:                        # noqa: BLE001 -- reported
        print(f"    {type(err).__name__}: {err}")
        return
    rows = ((payload.get("result") or payload).get("variables")
            or (payload.get("result") or payload).get("rows") or [])
    print(f"    {len(rows)} variable(s)")
    hits = []
    for row in rows:
        label = f"{row.get('name','')} {row.get('labl','')}".strip()
        if any(w in label.lower() for w in WANTED):
            hits.append((row.get("vid", "?"), label))
    if not hits:
        print("    none of religion/ethnicity/language named in any variable")
        return
    print(f"    {len(hits)} matching variable(s):")
    for vid, label in hits:
        print(f"      {str(vid):<10} {label[:90]}")
    print("    NOTE: a listed variable is microdata, not a published tabulation."
          " Downloading it commonly needs registration, and a survey is a sample"
          " with a stated universe rather than a census count.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", required=True, help="a NADA root, e.g. https://microdata.nigerianstat.gov.ng")
    ap.add_argument("--keyword", default="", help="search term; repeatable via commas")
    ap.add_argument("--study", default="", help="a study id; list its variables and stop")
    ap.add_argument("--limit", type=int, default=50)
    args = ap.parse_args()

    if args.study:
        variables(args.base, args.study)
        return 0
    for keyword in (args.keyword or "census,demographic,household,living").split(","):
        studies(args.base, keyword.strip(), args.limit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
