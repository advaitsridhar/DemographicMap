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
import base64
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
QUOTES = ("'", '"')
TIMEOUT = 90
USER_AGENT = ("DemographicMap/1.0 "
              "(+https://github.com/advaitsridhar/DemographicMap)")


def raw() -> str:
    value = (os.environ.get(KEY_VAR) or "").strip()
    if not value:
        raise SystemExit(
            f"probe_hapi: {KEY_VAR} is not set. HAPI wants an app identifier "
            f"-- base64 of 'appname:email', free from its /encode_app_identifier "
            f"endpoint. It is a repository secret and reaches this script "
            f"through the environment, never on a command line.")
    return value


def key() -> str:
    """The identifier in the form HAPI wants, from what the secret holds.

    The encode endpoint answers with a JSON object, not a bare string, so the
    obvious thing to put in a secret is the whole reply; and the obvious
    thing to paste from a browser is the quoted value. Both are recognised
    here rather than costing a round trip and a 403 to find out, and a raw
    "app:email" is encoded. Nothing about any of this is printed.
    """
    value = raw()
    if value.startswith("{"):
        try:
            value = str(json.loads(value).get("encoded_app_identifier") or "").strip()
        except ValueError:
            pass
    value = value.strip().strip('"').strip("'")
    if ":" in value and "@" in value:            # not encoded at all
        value = base64.b64encode(value.encode("utf-8")).decode("ascii")
    return value


def check() -> int:
    """What is in the secret, described and never shown.

    A 403 says the identifier is wrong and nothing else, and the one thing
    that must not happen while finding out which way it is wrong is printing
    it: it has an email address inside it and this log is committed in
    public. So this prints properties, not content.
    """
    value = raw()
    log(f"  {KEY_VAR}: {len(value)} characters")
    log(f"    looks like the encode endpoint's whole JSON reply: "
        f"{value.startswith('{')}")
    quoted = value[:1] in QUOTES
    log(f"    wrapped in quotes: {quoted}")
    log(f"    whitespace inside it: {any(c.isspace() for c in value)}")
    normalised = key()
    log(f"    after normalising: {len(normalised)} characters")
    try:
        decoded = base64.b64decode(normalised + "=" * (-len(normalised) % 4),
                                   validate=True).decode("utf-8")
    except Exception as err:                                  # noqa: BLE001
        log(f"    does not decode as base64 text: {type(err).__name__}")
        return 0
    log(f"    decodes to {len(decoded)} characters, "
        f"with a colon: {':' in decoded}, with an @: {'@' in decoded}, "
        f"in two parts: {len(decoded.split(':'))}")
    log("    (the decoded text itself is not printed: it carries an email "
        "address and this log is committed)")
    return 0


def scrub(text: str) -> str:
    """Anything printed, with the identifier taken out of it."""
    value = (os.environ.get(KEY_VAR) or "").strip()
    for secret in {value, key() if value else ""} - {""}:
        text = text.replace(secret, f"<{KEY_VAR}>")
    return text


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
    ap.add_argument("--check", action="store_true",
                    help="describe what the secret holds, without printing it")
    ap.add_argument("--rows", type=int, default=6)
    ap.add_argument("--width", type=int, default=400)
    args = ap.parse_args()
    if args.check:
        log("probe_hapi: describing the secret, not printing it")
        check()
        if not args.path:
            return 0
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
