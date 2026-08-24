#!/usr/bin/env python3
"""New Zealand -- Census 2023 ethnicity, religion and languages, by TA.

Stats NZ asks all three, and publishes them through Aotearoa Data Explorer's
SDMX API. Two dataflows carry what this map wants, both broken down by the
geography geoBoundaries happens to use for New Zealand:

    CEN23_ECI_017   religious affiliation x ethnicity x gender
    CEN23_ECI_011   languages spoken x ethnicity x gender

**The API needs a key.** Only the bare dataflow catalogue is open; every
``/data/``, ``/datastructure/`` and ``?references=`` request is 401 without
one, because the Explorer's public member is captcha-gated. The key is read
from the environment (see ``KEY_VARS``) and sent as an Azure API Management
subscription header. It is never written to a file, a log or a command line.

**The geography is the one CGAZ has.** Stats NZ publishes census tables at
"territorial authority and Auckland local board area" -- 67 territorial
authorities with Auckland replaced by its 21 local boards -- and that is
exactly the 88-shape admin-2 layer geoBoundaries ships for New Zealand. No
other country in this project has lined up that neatly.

**Two things about the counts.** Ethnicity and languages are multi-response:
a person may name several, so the parts sum to more than the whole and the
shares are of responses rather than of people. And Stats NZ applies random
rounding to base 3 and suppresses small cells, which arrives as an
``OBS_STATUS`` of ``c`` (confidential) or ``_U`` (unavailable) rather than as
a zero -- a suppressed cell is a gap, not an absence.
"""

from __future__ import annotations

import argparse
import csv
import io
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from ._shared import PROCESSED, log, write_json

BASE = "https://api.data.stats.govt.nz/rest"
AGENCY = "STATSNZ"
YEAR = 2023
SOURCE = "Stats NZ, 2023 Census (Aotearoa Data Explorer)"
LICENSE = ("Creative Commons Attribution 4.0 International, "
           "as published by Stats NZ")
TIMEOUT = 180

# Environment variables that might carry the key, in the order they are tried.
KEY_VARS = ("NZ_STATS_API", "STATS_NZ_API_KEY", "STATSNZ_API_KEY",
            "STATS_NZ_KEY", "STATSNZ_KEY", "NZ_STATS_API_KEY")

# Stats NZ sits behind Azure API Management.
KEY_HEADER = "Ocp-Apim-Subscription-Key"

# SDMX-CSV rather than the XML: one header row naming the dimensions, then one
# row per observation, which is all this needs.
CSV_ACCEPT = "application/vnd.sdmx.data+csv;version=1.0.0"
XML_ACCEPT = "application/vnd.sdmx.structure+xml;version=2.1"

FLOWS = {
    "religion": "CEN23_ECI_017",
    "language": "CEN23_ECI_011",
}

# A suppressed or unavailable cell is not a zero. Stats NZ randomly rounds
# every count to base 3 and withholds cells too small to publish; reading
# either as an absence would turn "we will not say" into "nobody".
SUPPRESSED = {"c", "_U", "..", "C"}


def api_key() -> str:
    for name in KEY_VARS:
        value = (os.environ.get(name) or "").strip()
        if value:
            log(f"  key from {name} ({len(value)} characters)")
            return value
    raise SystemExit(
        "No Stats NZ API key in the environment. Aotearoa Data Explorer "
        "refuses every data request without one.\n"
        f"Set one of: {', '.join(KEY_VARS)}\n"
        "In CI it comes from a repository secret passed through the "
        "workflow's env block, never on a command line.")


def fetch(path: str, *, accept: str, key: str) -> str:
    url = f"{BASE}/{path}"
    req = urllib.request.Request(url, headers={
        "Accept": accept,
        "Accept-Encoding": "identity",
        "User-Agent": "DemographicMap/1.0 (+https://github.com/"
                      "advaitsridhar/DemographicMap)",
        KEY_HEADER: key,
    })
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as err:
        body = err.read().decode("utf-8", "replace")[:300]
        # The URL is safe to print; the key is a header and never in it.
        raise SystemExit(f"{url}\n  HTTP {err.code}: {body}") from err


def structure(flow: str, key: str) -> str:
    """The dataflow with every codelist it references."""
    return fetch(f"dataflow/{AGENCY}/{flow}/1.0?references=all",
                 accept=XML_ACCEPT, key=key)


def observations(flow: str, selection: str, key: str) -> list[dict[str, str]]:
    """One SDMX query, as rows keyed by the dimension ids in the header."""
    text = fetch(f"data/{AGENCY},{flow},1.0/{selection}",
                 accept=CSV_ACCEPT, key=key)
    rows = list(csv.DictReader(io.StringIO(text)))
    log(f"  {flow} [{selection}]: {len(rows):,} observations")
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dump-structure", choices=sorted(FLOWS),
                    help="write the dataflow's codelists somewhere readable "
                         "and stop; this is how the codes below were found")
    ap.add_argument("--dump-data", choices=sorted(FLOWS),
                    help="write one query's rows and stop")
    ap.add_argument("--selection", default="all",
                    help="SDMX key, dimensions dot-separated in order")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    key = api_key()

    if args.dump_structure:
        flow = FLOWS[args.dump_structure]
        text = structure(flow, key)
        out = args.out or (PROCESSED / f"nz-{flow}-structure.xml")
        out.write_text(text, encoding="utf-8")
        log(f"  wrote {out} ({len(text):,} bytes)")
        return 0

    if args.dump_data:
        flow = FLOWS[args.dump_data]
        text = fetch(f"data/{AGENCY},{flow},1.0/{args.selection}",
                     accept=CSV_ACCEPT, key=key)
        out = args.out or (PROCESSED / f"nz-{flow}-data.csv")
        out.write_text(text, encoding="utf-8")
        log(f"  wrote {out} ({len(text):,} bytes)")
        return 0

    raise SystemExit("nothing to build yet: run --dump-structure first")


if __name__ == "__main__":
    raise SystemExit(main())
