"""Iraq's districts: the 2024 census, from the Annual Abstract of Statistics.

Iraq counted its people in November 2024, the first census since 1997, and
COSIT prints the result in Part Two of its Annual Abstract of Statistics 2024:
Table 11/2 gives every sub-district (nahiya) its population, by sex and by
urban and rural, under its district (qadhaa) and governorate, each with its
COSIT code. OCHA's population tables for Iraq stop at the governorate, and
Wikidata has no figure for most districts, so 86 of the map's 101 were blank.

``--dump`` writes the table's pages as laid-out text to data/raw/iraq, which
is what the parser is written against.

Usage:
    python -m scripts.fetch_census.iraq_census --dump
    python -m scripts.fetch_census.iraq_census
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ._shared import log

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from probe_pdf import PAGE_BREAK, fetch_blob, laid_out  # noqa: E402

URL = "https://cosit.gov.iq/documents/AAS2024/02.pdf"
ROOT = Path(__file__).resolve().parent.parent.parent
DUMP = ROOT / "data" / "raw" / "iraq" / "aas2024_table11.txt"


def table_pages(text: str) -> list[str]:
    """The pages of Table 11/2: those whose header names a nahiya."""
    return [page for page in text.split(PAGE_BREAK) if "Nahiya" in page]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dump", action="store_true")
    args = ap.parse_args()
    blob = fetch_blob(URL)
    log(f"  {URL}: {len(blob):,} bytes")
    pages = table_pages(laid_out(blob))
    log(f"  {len(pages)} pages of Table 11/2")
    if args.dump:
        DUMP.parent.mkdir(parents=True, exist_ok=True)
        DUMP.write_text(PAGE_BREAK.join(pages), encoding="utf-8")
        log(f"  wrote {DUMP.relative_to(ROOT)}")
        return 0
    raise SystemExit("the parser is not written yet; run with --dump")


if __name__ == "__main__":
    raise SystemExit(main())
