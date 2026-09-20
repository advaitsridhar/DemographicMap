#!/usr/bin/env python3
"""Mongolia: ethnicity, religion and language by aimag and soum.

Work in progress; ``--probe`` is the reconnaissance and writes nothing.

The National Statistical Office's statistical database used to be
``opendata.1212.mn``; that hostname no longer resolves. ``nso.mn`` and
``www.1212.mn`` now serve one Next.js application whose own links name
``data.nso.mn`` (the database) and ``metadata.nso.mn``. Every ``*.nso.mn``
and ``*.1212.mn`` host sends its leaf certificate without the Sectigo
intermediate above it, so a plain urllib client fails them with *unable to
get local issuer certificate*; ``common.http_get(..., aia=True)`` completes
the chain from the certificate's own Authority Information Access extension
and verifies, which is what every request here uses.

Usage:
    python -m scripts.fetch_census.mongolia --probe --get https://data.nso.mn/
    python -m scripts.fetch_census.mongolia --probe --post https://data.nso.mn/api/Data
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from ._shared import log
from common import http_get  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

BYTES = 3000
AGENT = "DemographicMap/1.0 (+https://github.com/advaitsridhar/DemographicMap)"


def fetch(url: str, *, limit: int = BYTES, find: str | None = None,
          terms: list[str] | None = None, context: int = 200,
          headers: dict[str, str] | None = None) -> str | None:
    try:
        body = http_get(url, cache=False, retries=1, timeout=60, aia=True, headers=headers)
    except Exception as exc:                # noqa: BLE001 - the probe's product is the reason
        log(f"  {url}\n    unreachable: {type(exc).__name__}: {exc}")
        return None
    text = body if isinstance(body, str) else body.decode("utf-8", "replace")
    log(f"  {url}\n    {len(text):,} chars")
    if find:
        import re                                  # noqa: PLC0415
        hits = sorted({m.group(0) for m in re.finditer(find, text)})
        log(f"    {len(hits)} distinct match(es) for {find!r}")
        for hit in hits[:200]:
            log(f"      {hit}")
    elif terms:
        for term in terms:
            seen = 0
            at = text.find(term)
            while at >= 0 and seen < 12:
                lo, hi = max(0, at - context), min(len(text), at + len(term) + context)
                log(f"    [{term} @{at}] ...{text[lo:hi]}...")
                seen += 1
                at = text.find(term, at + 1)
            if not seen:
                log(f"    [{term}] not present")
    else:
        log("    " + text[:limit].replace("\n", "\n    "))
    return text


def post(url: str, payload: dict[str, Any], *, limit: int = BYTES) -> str | None:
    from probe_tls import verified_opener          # noqa: PLC0415
    blob = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=blob, headers={
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": AGENT,
    })
    opener = verified_opener(urllib.parse.urlsplit(url).hostname or "")
    try:
        with opener.open(req, timeout=120) as resp:
            text = resp.read().decode("utf-8", "replace")
            log(f"  POST {url} {payload}\n    {resp.status} {len(text):,} chars")
    except Exception as exc:                       # noqa: BLE001
        log(f"  POST {url} {payload}\n    failed: {type(exc).__name__}: {exc}")
        return None
    log("    " + text[:limit].replace("\n", "\n    "))
    return text


def probe(args: argparse.Namespace) -> int:
    for url in args.get or []:
        fetch(url, limit=args.bytes, find=args.find,
              terms=args.terms.split(",") if args.terms else None,
              context=args.context)
    payload = dict(kv.split("=", 1) for kv in (args.field or []))
    for url in args.post or []:
        post(url, payload, limit=args.bytes)
    return 0


def run() -> int:
    raise SystemExit("mongolia: no data route settled yet; run with --probe")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--get", action="append")
    ap.add_argument("--post", action="append")
    ap.add_argument("--field", action="append", help="NAME=VALUE for a POST body")
    ap.add_argument("--find", help="print the distinct matches of this regex instead of the body")
    ap.add_argument("--terms", help="comma-separated words to print the surroundings of")
    ap.add_argument("--context", type=int, default=200)
    ap.add_argument("--bytes", type=int, default=BYTES)
    args = ap.parse_args()
    return probe(args) if args.probe else run()


if __name__ == "__main__":
    raise SystemExit(main())
