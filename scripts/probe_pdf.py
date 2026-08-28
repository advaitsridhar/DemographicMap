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

    pypdf's plain extraction returns a page's strings in the order the file
    happens to store them, which for these census tables is every number
    first and then every row label in a block at the end:

        ...
        HAVELIAN TEHSIL
        TABLE 9 : POPULATION BY SEX, RELIGION...
        ABBOTTABAD DISTRICT
        ABBOTTABAD TEHSIL

    Pairing those with the figures by their order in that list is a guess, and
    the table interleaves districts with the tehsils inside them, so a wrong
    guess does not look wrong -- it puts a tehsil's people on a district. The
    positions are in the file, so they are read instead: every fragment is
    collected with the y it was drawn at, fragments sharing a y to within a
    couple of points are one row, and the row is written left to right.
    """
    import io
    from pypdf import PdfReader

    out: list[str] = []
    for page in PdfReader(io.BytesIO(blob)).pages:
        parts: list[tuple[float, float, str]] = []

        def visit(text, cm, tm, font_dict, font_size, _parts=parts):
            # The text matrix positions a fragment inside the current
            # transformation, so tm[5] alone is only the y when the CTM happens
            # to be the identity. Reading it that way lost the whole TOTAL
            # POPULATION column and every figure under the first district
            # heading -- text drawn inside a transformed form landed at a y
            # that matched nothing, so its row was never assembled.
            if not text or not text.strip():
                return
            x = cm[0] * tm[4] + cm[2] * tm[5] + cm[4]
            y = cm[1] * tm[4] + cm[3] * tm[5] + cm[5]
            _parts.append((round(y, 1), round(x, 1), text.strip()))

        page.extract_text(visitor_text=visit)
        rows: list[tuple[float, list[tuple[float, str]]]] = []
        for y, x, text in sorted(parts, key=lambda p: (-p[0], p[1])):
            if rows and abs(rows[-1][0] - y) <= tolerance:
                rows[-1][1].append((x, text))
            else:
                rows.append((y, [(x, text)]))
        for _y, cells in rows:
            out.append(" ".join(t for _x, t in sorted(cells)))
        # Said per page, because a page that yields far fewer fragments than
        # its neighbours is the signature of text this reader cannot see.
        out.append(f"[{len(parts)} fragments in {len(rows)} rows]")
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
