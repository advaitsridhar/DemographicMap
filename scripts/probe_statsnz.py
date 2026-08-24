#!/usr/bin/env python3
"""What Stats NZ's SDMX API answers once a key is present.

Aotearoa Data Explorer publishes New Zealand's census through a .Stat Suite
SDMX API at ``api.data.stats.govt.nz``. Only the bare dataflow catalogue is
open: every ``/data/``, ``/datastructure/`` and ``?references=`` request comes
back 401, and the Explorer's own page config says why -- the public member is
captcha-gated. A key lifts that.

This reports whether a key was found, which header the service accepts it in,
and what one small slice of a dataflow actually looks like. It is read-only,
and it never prints the key: only whether one was found and how long it is,
which is enough to tell a missing secret from a rejected one.

Usage:
    python scripts/probe_statsnz.py --flow CEN23_ECI_017
"""

from __future__ import annotations

import argparse
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import log  # noqa: E402

BASE = "https://api.data.stats.govt.nz/rest"
TIMEOUT = 45

# Environment variables that might carry the key, in the order they are tried.
# Several, because the repository secret's name is the author's choice and a
# probe that insists on one spelling fails for a reason that looks like a
# rejected key.
KEY_VARS = ("NZ_STATS_API", "STATS_NZ_API_KEY", "STATSNZ_API_KEY",
            "STATS_NZ_KEY", "STATSNZ_KEY", "NZ_STATS_API_KEY",
            "DEMOGRAPHICMAP_NZ", "AOTEAROA_DATA_EXPLORER_KEY")

# Header names .Stat Suite deployments use for a subscription key. Stats NZ
# sits behind Azure API Management, which is the first of these; the others
# cost nothing to try and save a round trip if it has moved.
HEADERS = ("Ocp-Apim-Subscription-Key", "Subscription-Key", "x-api-key",
           "api-key")

# SDMX-CSV is asked for by content negotiation rather than a query parameter,
# and is far easier to read back than the XML.
ACCEPT = "application/vnd.sdmx.data+csv;version=1.0.0"


def find_key() -> tuple[str, str] | tuple[None, None]:
    for name in KEY_VARS:
        value = (os.environ.get(name) or "").strip()
        if value:
            return name, value
    return None, None


def request(url: str, key: str | None, header: str | None,
            accept: str = "") -> tuple[int, str]:
    headers = {"User-Agent": "DemographicMap/1.0 (+https://github.com/"
                             "advaitsridhar/DemographicMap)"}
    if accept:
        headers["Accept"] = accept
    if key and header:
        headers[header] = key
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as err:
        return err.code, err.read().decode("utf-8", "replace")[:400]
    except Exception as err:                      # noqa: BLE001
        return 0, f"{type(err).__name__}: {str(err)[:200]}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--flow", default="CEN23_ECI_017")
    ap.add_argument("--agency", default="STATSNZ")
    ap.add_argument("--version", default="1.0")
    ap.add_argument("--rows", type=int, default=40,
                    help="lines of the data response to print")
    args = ap.parse_args()

    name, key = find_key()
    if key:
        log(f"  key found in {name} ({len(key)} characters)")
    else:
        log(f"  no key in any of: {', '.join(KEY_VARS)}")

    flow = f"{args.agency},{args.flow},{args.version}"
    targets = [
        ("dataflow (known to be open)",
         f"{BASE}/dataflow/{args.agency}/{args.flow}/{args.version}", ""),
        ("dataflow + references",
         f"{BASE}/dataflow/{args.agency}/{args.flow}/{args.version}"
         "?references=all", ""),
        ("data, SDMX-CSV", f"{BASE}/data/{flow}/all", ACCEPT),
    ]

    working: str | None = None
    for label, url, accept in targets:
        log(f"\n  {label}")
        log(f"    {url}")
        for header in (HEADERS if key else (None,)):
            status, body = request(url, key, header, accept)
            shown = header or "no key"
            log(f"    {shown:<28} HTTP {status}")
            if status == 200:
                working = header
                head = "\n".join(body.splitlines()[:args.rows])
                log(f"    --- first {args.rows} lines ---\n{head}\n    --- end ---")
                break
            if status == 0:
                log(f"      {body}")
        else:
            continue

    if key and working:
        log(f"\n  the service accepts the key in: {working}")
    elif key:
        log("\n  a key was found and every request was still refused; either "
            "the key is not valid for this API or it is sent another way")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
