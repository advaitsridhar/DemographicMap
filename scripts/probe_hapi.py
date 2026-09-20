#!/usr/bin/env python3
"""What the Humanitarian API serves, and -- first -- under what licence.

HDX's CKAN catalogue at data.humdata.org is one thing; HAPI, at
hapi.humdata.org, is another: a standardised read-only API over a subset of
the same material, with every row carrying the dataset and resource it came
from. It wants an "app identifier", which is base64 of "appname:email" and is
free to generate.

**The identifier never appears in this script's output.** It is read from
``DEMOGRAPHIC_MAP`` in the environment, never from a command line, and every
line this prints goes through ``scrub()``. That is not only the usual rule
about credentials: the identifier has the owner's email address inside it,
and this script's whole product is a log that gets committed to a public
repository.

**A key is access, not permission.** HAPI serves data from many publishers
and the licence is the publisher's, not HAPI's: Indonesia's subnational
population on HDX is "humanitarian use only" with ``isopen: false``, and no
credential changes that. So this probe prints the provenance of what it
fetches -- dataset, resource, provider -- before anything is read from it,
and an adapter built on HAPI has to check the licence of each country it
touches rather than the API it came through.

Read-only. The output is the log.

Usage:
    python -m scripts.probe_hapi --path metadata/dataset --params "limit=5"
    python -m scripts.probe_hapi --path population-social/population \\
        --params "location_code=IDN&admin_level=2&limit=5"
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import log  # noqa: E402

BASE = "https://hapi.humdata.org/api/v2"
KEY_VAR = "DEMOGRAPHIC_MAP"
TIMEOUT = 90
USER_AGENT = ("DemographicMap/1.0 "
              "(+https://github.com/advaitsridhar/DemographicMap)")


def key() -> str:
    value = (os.environ.get(KEY_VAR) or "").strip()
    if not value:
        raise SystemExit(
            f"probe_hapi: {KEY_VAR} is not set. HAPI wants an app identifier "
            f"-- base64 of 'appname:email', free from its /encode_app_identifier "
            f"endpoint. It is a repository secret and reaches this script "
            f"through the environment, never on a command line.")
    return value


def scrub(text: str) -> str:
    """Anything printed, with the identifier taken out of it."""
    value = (os.environ.get(KEY_VAR) or "").strip()
    return text.replace(value, f"<{KEY_VAR}>") if value else text


def call(path: str, params: dict[str, str]) -> Any:
    query = dict(params)
    query["app_identifier"] = key()
    url = f"{BASE}/{path}?" + urllib.parse.urlencode(query)
    request = urllib.request.Request(
        url, headers={"Accept": "application/json", "User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            body = response.read()
    except urllib.error.HTTPError as err:
        detail = err.read().decode("utf-8", "replace")[:600]
        return {"__error__": scrub(f"HTTP {err.code} {err.reason or ''}: {detail}")}
    except Exception as err:                                  # noqa: BLE001
        return {"__error__": scrub(f"{type(err).__name__}: {err}")}
    try:
        return json.loads(body)
    except ValueError:
        return {"__error__": scrub(f"not JSON: {len(body)} bytes; "
                                   f"{body[:300].decode('utf-8', 'replace')}")}


def show(path: str, params: dict[str, str], rows: int, width: int) -> None:
    log(f"  {BASE}/{path}?" + urllib.parse.urlencode(params))
    body = call(path, params)
    if isinstance(body, dict) and "__error__" in body:
        log(f"    refused: {body['__error__']}")
        return
    data = body.get("data") if isinstance(body, dict) else body
    if data is None:
        log(f"    {scrub(json.dumps(body))[:width * 4]}")
        return
    log(f"    {len(data)} row(s)")
    for row in data[:rows]:
        flat = ", ".join(f"{k}={v!r}" for k, v in row.items() if v not in (None, ""))
        log(f"    {scrub(flat)[:width]}")


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--path", action="append", default=[],
                    help="an endpoint under /api/v2, e.g. metadata/dataset")
    ap.add_argument("--params", action="append", default=[],
                    help="query string for the matching --path, e.g. "
                         "'location_code=IDN&admin_level=2&limit=5'")
    ap.add_argument("--rows", type=int, default=6)
    ap.add_argument("--width", type=int, default=400)
    args = ap.parse_args()
    if not args.path:
        raise SystemExit("probe_hapi: give at least one --path")
    log(f"probe_hapi: {len(args.path)} call(s); the app identifier is read from "
        f"{KEY_VAR} and scrubbed from everything below")
    for index, path in enumerate(args.path):
        raw = args.params[index] if index < len(args.params) else ""
        params = dict(urllib.parse.parse_qsl(raw))
        show(path.strip("/"), params, args.rows, args.width)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
