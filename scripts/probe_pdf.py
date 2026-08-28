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
    python scripts/probe_pdf.py --url https://example.org/table.pdf --terms religion
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import log  # noqa: E402

PAGE_BREAK = "\f"


def laid_out(blob: bytes, tolerance: float = 2.0) -> str:
    """A PDF as text with the rows put back together from their coordinates.

    pypdf returns a page's strings in whatever order the file stores them,
    which for these census tables is every number first and every row label
    afterwards, in a block at the end of the page:

        HAVELIAN TEHSIL
        TABLE 9 : POPULATION BY SEX, RELIGION...
        ABBOTTABAD DISTRICT
        ABBOTTABAD TEHSIL

    Pairing those with the figures by their order in that list is a guess, and
    that list is not even in document order -- Havelian, the last tehsil on the
    page, comes first. The table also interleaves districts with the tehsils
    inside them, so a wrong pairing does not look wrong: it puts a tehsil's
    people on a district and every total still adds up.

    pypdf's own visitor cannot supply the positions either -- it is never
    called for some of these fragments, and reading its text matrix lost the
    whole TOTAL POPULATION column while leaving perfectly well-formed rows
    behind. pdfplumber reports every word with its box, so the rows are
    assembled from where the words actually sit: words sharing a baseline to
    within a couple of points are one row, written left to right.
    """
    import io

    import pdfplumber

    out: list[str] = []
    with pdfplumber.open(io.BytesIO(blob)) as pdf:
        log(f"  {len(pdf.pages)} pages")
        for page in pdf.pages:
            words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
            rows: list[tuple[float, list[tuple[float, str]]]] = []
            for word in sorted(words, key=lambda w: (round(w["top"], 1), w["x0"])):
                top = round(word["top"], 1)
                if rows and abs(rows[-1][0] - top) <= tolerance:
                    rows[-1][1].append((word["x0"], word["text"]))
                else:
                    rows.append((top, [(word["x0"], word["text"])]))
            for _top, cells in rows:
                out.append(" ".join(t for _x, t in sorted(cells)))
            # Said per page, because a page yielding far fewer words than its
            # neighbours is the signature of text this reader cannot see.
            out.append(f"[{len(words)} words in {len(rows)} rows]")
            out.append(PAGE_BREAK)
    return "\n".join(out)


def fetch_text(url: str, layout: bool = False) -> str:
    """A remote PDF as text, page by page, without keeping the file.

    The machine that can reach a statistical office is not the machine that
    builds the site, so a probe that insists on a local file cannot be pointed
    at the thing it is meant to describe. pypdf rather than pdftotext for the
    same reason the adapters use it: a pip dependency travels with the
    repository and a system package does not.
    """
    import io
    import urllib.request
    from pypdf import PdfReader

    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; DemographicMap/1.0; "
                      "+https://github.com/advaitsridhar/DemographicMap)",
        "Accept": "application/pdf,*/*",
    })
    with urllib.request.urlopen(req, timeout=90) as resp:
        blob = resp.read()
    log(f"  {len(blob):,} bytes")
    if layout:
        return laid_out(blob)
    reader = PdfReader(io.BytesIO(blob))
    log(f"  {len(reader.pages)} pages")
    return PAGE_BREAK.join((page.extract_text() or "") for page in reader.pages)


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
    ap.add_argument("text", type=Path, nargs="?",
                    help="output of pdftotext -layout")
    ap.add_argument("--url", help="fetch and read a PDF instead of a local file")
    ap.add_argument("--layout", action="store_true",
                    help="rebuild rows from the glyphs' coordinates, so a row "
                         "label stays with the figures it labels")
    ap.add_argument("--terms", default="language,mother tongue,speak",
                    help="comma-separated terms to find pages for")
    ap.add_argument("--contents", type=int, default=120,
                    help="lines of the front matter to print")
    ap.add_argument("--max-pages", type=int, default=12)
    ap.add_argument("--excerpt", type=int, default=2500)
    args = ap.parse_args()

    if args.url:
        log(f"probe_pdf: {args.url}")
        text = fetch_text(args.url, layout=args.layout)
    elif args.text:
        text = args.text.read_text(encoding="utf-8", errors="replace")
    else:
        ap.error("give a text file or --url")
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
