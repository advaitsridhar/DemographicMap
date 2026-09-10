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


def studies(base: str, keyword: str, limit: int, raw: bool = False) -> list[dict]:
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
    if rows and raw:
        # Every identifier the catalogue publishes for a study, printed once.
        # The detail endpoints refuse the numeric id with 400, and which field
        # they do want is not guessable from the outside -- so read the record
        # rather than try a fifth URL shape.
        print("    --- first row, verbatim ---")
        print("    " + json.dumps(rows[0], indent=2)[:2000].replace("\n", "\n    "))
        print("    --- end ---")
    for row in rows:
        # var_found is the whole point: NADA's search matches variable labels
        # as well as titles, so a keyword like "religion" reports how many of a
        # study's variables carry it. That answers "was the question asked"
        # without the detail endpoints, which refuse the numeric id with 400.
        print(f"    id={str(row.get('id','?')):<5} {str(row.get('year_end') or row.get('year_start') or '?'):<5} "
              f"vars={str(row.get('varcount','?')):<6} hits={str(row.get('var_found','0')):<4} "
              f"{str(row.get('form_model','?')):<10} {str(row.get('title',''))[:64]}")
    return rows


def variables(base: str, study: str) -> None:
    """The variable list, which is what says whether a question was asked.

    NADA's variable path is not the same across versions, and a guessed path
    answers 400 -- which is a fact about the request, not about the survey.
    So this asks the study record first and prints what it actually offers
    before trying anything, then reports each candidate path separately: a 404
    means "not here", a 400 means "not asked like that", and the difference
    decides whether to try another shape or stop.
    """
    root = base.rstrip("/")
    print(f"\n=== NADA study record: {study} ===")
    try:
        record = get(f"{root}/index.php/api/catalog/{study}")
        body = record.get("dataset") or record.get("result") or record
        print(f"    top-level keys: {sorted(body)[:24]}")
        for key in ("title", "idno", "nation", "year_start", "year_end"):
            if body.get(key):
                print(f"    {key}: {str(body[key])[:90]}")
        for key in ("resources", "data_files", "variables", "var_count"):
            value = body.get(key)
            if isinstance(value, list):
                print(f"    {key}: {len(value)} entry(ies)")
                for item in value[:12]:
                    if isinstance(item, dict):
                        print(f"      {str(item.get('name') or item.get('file_id') or item)[:88]}")
            elif value is not None:
                print(f"    {key}: {value}")
    except Exception as err:                        # noqa: BLE001 -- reported
        print(f"    {type(err).__name__}: {err}")

    print(f"\n=== NADA variables: study {study} ===")
    payload = None
    for path in (f"{root}/index.php/api/catalog/{study}/variables",
                 f"{root}/index.php/api/catalog/variables/{study}",
                 f"{root}/index.php/api/datasets/{study}/variables"):
        try:
            payload = get(path)
            print(f"    answered: {path}")
            break
        except Exception as err:                    # noqa: BLE001 -- reported
            print(f"    {type(err).__name__}: {err}  <- {path}")
    if payload is None:
        print("    no variable endpoint answered; the study record above is what"
              " this catalogue offers a program")
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
    ap.add_argument("--raw", action="store_true",
                    help="dump the first search row verbatim, to see what identifiers exist")
    args = ap.parse_args()

    if args.study:
        variables(args.base, args.study)
        return 0
    for keyword in (args.keyword or "census,demographic,household,living").split(","):
        studies(args.base, keyword.strip(), args.limit, args.raw)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
