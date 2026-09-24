"""Uzbekistan's districts: permanent population from the Statistics Agency's SIAT.

The agency's open-data portal (siat.stat.uz) publishes indicator 2.01.02.0001,
the permanent population at the start of each year, for every region, city
and district, keyed by SOATO code, under CC BY 4.0. OCHA's population table
for Uzbekistan names the districts and carries no figure, and Wikidata has
none for most of them, so 163 of the map's 198 were blank.

``--dump`` saves the agency's JSON to data/raw/uzbekistan, which is what the
parser is written against.

Usage:
    python -m scripts.fetch_census.uzbekistan_siat --dump
    python -m scripts.fetch_census.uzbekistan_siat
"""
from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path

from ._shared import log

INDICATOR = 246
POINTER = f"https://api.siat.stat.uz/sdmx/{INDICATOR}/table/download/?download_format=json"
ROOT = Path(__file__).resolve().parent.parent.parent
DUMP = ROOT / "data" / "raw" / "uzbekistan" / f"siat_{INDICATOR}.json"
HEADERS = {"User-Agent": "DemographicMap/1.0 (+https://github.com/advaitsridhar/DemographicMap)",
           "Accept": "application/json"}
TIMEOUT = 120


def get(url: str) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS),
                                timeout=TIMEOUT) as fh:
        return fh.read()


def download() -> bytes:
    """The data file the download link points to."""
    pointer = json.loads(get(POINTER))
    url = pointer.get("file") or pointer.get("file_2")
    log(f"  {POINTER} -> {url} ({pointer.get('size')}, updated {pointer.get('updated_at')})")
    return get(url)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dump", action="store_true")
    args = ap.parse_args()
    blob = download()
    data = json.loads(blob)
    log(f"  {len(blob):,} bytes; top level {type(data).__name__} of {len(data)}")
    if args.dump:
        DUMP.parent.mkdir(parents=True, exist_ok=True)
        DUMP.write_bytes(blob)
        log(f"  wrote {DUMP.relative_to(ROOT)}")
        return 0
    raise SystemExit("the parser is not written yet; run with --dump")


if __name__ == "__main__":
    raise SystemExit(main())
