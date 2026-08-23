#!/usr/bin/env python3
"""Report what a statistical report PDF contains, without downloading it here.

Statistical offices publish a great deal of their real numbers only inside
report PDFs. Before deciding whether one is worth an adapter, it is worth
knowing what is actually in it: how many pages, what the contents listing
promises, and which pages mention the thing you are after.

This reads a PDF that has already been converted to text (``pdftotext -layout``,
which preserves column alignment well enough that census tables survive) and
prints the pages matching the terms given. As with ``probe_arcgis.py``, nothing
is written and nothing is committed -- the output is the log.

Usage:
    pdftotext -layout report.pdf report.txt
    python scripts/probe_pdf.py report.txt --terms "language,mother tongue"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import log  # noqa: E402

PAGE_BREAK = "\f"


def pages(text: str) -> list[str]:
    return text.split(PAGE_BREAK)


def matching(text: str, terms: list[str]) -> list[tuple[int, str]]:
    lowered = [t.lower() for t in terms if t]
    return [(number, page) for number, page in enumerate(pages(text), 1)
            if any(term in page.lower() for term in lowered)]


def condense(page: str, limit: int) -> str:
    """Drop blank lines so a sparse census table fits the excerpt budget."""
    body = "\n".join(line.rstrip() for line in page.splitlines() if line.strip())
    return body[:limit]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("text", type=Path, help="output of pdftotext -layout")
    ap.add_argument("--terms", default="language,mother tongue,speak",
                    help="comma-separated terms to find pages for")
    ap.add_argument("--contents", type=int, default=120,
                    help="lines of the front matter to print")
    ap.add_argument("--max-pages", type=int, default=12)
    ap.add_argument("--excerpt", type=int, default=2500)
    args = ap.parse_args()

    text = args.text.read_text(encoding="utf-8", errors="replace")
    terms = [t.strip() for t in args.terms.split(",") if t.strip()]
    all_pages = pages(text)
    hits = matching(text, terms)

    log(f"probe_pdf: {len(all_pages)} pages, {len(hits)} mention {terms}")
    log("=== front matter ===")
    log("\n".join(text.splitlines()[: args.contents]))

    log(f"\n=== pages mentioning {terms} (first {args.max_pages}) ===")
    for number, page in hits[: args.max_pages]:
        log(f"\n--- page {number} " + "-" * 52)
        log(condense(page, args.excerpt))
    if len(hits) > args.max_pages:
        log(f"\n... and {len(hits) - args.max_pages} further pages match; "
            f"re-run with a narrower --terms to see them.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
