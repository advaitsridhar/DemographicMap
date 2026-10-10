#!/usr/bin/env python3
"""Read-only probes for the round's new census reads: what a PDF or a page holds.

``pdf``: fetch a PDF, say how many pages it has, and print the lines of each
page (or of the pages asked for) that match a pattern -- enough to see which
table a release carries and how its rows read, before a reader is written.

``page``: fetch a page and print the parts of its body matching a pattern
(links to documents a script-built page names only in its markup).

``xlsx``: fetch a workbook and print its sheets and the rows matching a
pattern.

Nothing is written. The output is the log.

Usage:
    python -m scripts.fetch_census.r6_probe pdf URL --grep REGEX [--pages 1-20] [--aia]
    python -m scripts.fetch_census.r6_probe page URL --grep REGEX [--aia]
    python -m scripts.fetch_census.r6_probe xlsx URL --grep REGEX [--aia]
"""

from __future__ import annotations

import argparse
import io
import re

from ._shared import http_get, log


def pages(spec: str | None, n: int) -> list[int]:
    if not spec:
        return list(range(n))
    out: list[int] = []
    for part in spec.split(","):
        lo, _, hi = part.partition("-")
        out += list(range(int(lo) - 1, min(n, int(hi or lo))))
    return out


def probe_pdf(url: str, grep: str, spec: str | None, aia: bool, limit: int) -> None:
    import pdfplumber                               # noqa: PLC0415
    blob = http_get(url, binary=True, timeout=300, aia=aia, cache=False)
    log(f"{url}: {len(blob):,} bytes, starts {blob[:8]!r}")
    if not blob.startswith(b"%PDF"):
        log(f"  not a PDF: {blob[:200]!r}")
        return
    pattern = re.compile(grep, re.I)
    shown = 0
    with pdfplumber.open(io.BytesIO(blob)) as pdf:
        log(f"  {len(pdf.pages)} pages")
        for i in pages(spec, len(pdf.pages)):
            text = pdf.pages[i].extract_text() or ""
            for line in text.splitlines():
                if pattern.search(line):
                    log(f"  p{i + 1}: {line[:160]}")
                    shown += 1
                    if shown >= limit:
                        log("  (limit reached)")
                        return


def probe_page(url: str, grep: str, aia: bool, limit: int) -> None:
    text = http_get(url, timeout=120, aia=aia, cache=False)
    log(f"{url}: {len(text):,} characters")
    found = []
    for m in re.finditer(grep, text, re.I):
        hit = m.group(0)
        if hit not in found:
            found.append(hit)
    for hit in found[:limit]:
        log(f"  {hit[:200]}")
    log(f"  {len(found)} distinct match(es)")


def probe_xlsx(url: str, grep: str, aia: bool, limit: int) -> None:
    blob = http_get(url, binary=True, timeout=300, aia=aia, cache=False)
    log(f"{url}: {len(blob):,} bytes, starts {blob[:8]!r}")
    pattern = re.compile(grep, re.I)
    shown = 0
    if blob[:2] == b"PK":
        import openpyxl                             # noqa: PLC0415
        book = openpyxl.load_workbook(io.BytesIO(blob), read_only=True, data_only=True)
        sheets = [(ws.title, ws.iter_rows(values_only=True)) for ws in book.worksheets]
    else:
        import xlrd                                 # noqa: PLC0415
        book = xlrd.open_workbook(file_contents=blob)
        sheets = [(s.name, (s.row_values(r) for r in range(s.nrows))) for s in book.sheets()]
    for title, rows in sheets:
        log(f"  sheet {title!r}")
        for r, row in enumerate(rows):
            line = " | ".join("" if c is None else str(c) for c in row).strip(" |")
            if r < 4 or pattern.search(line):
                log(f"    r{r + 1}: {line[:200]}")
                shown += 1
                if shown >= limit:
                    log("  (limit reached)")
                    return


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("kind", choices=("pdf", "page", "xlsx"))
    ap.add_argument("url", nargs="+")
    ap.add_argument("--grep", default=".")
    ap.add_argument("--pages")
    ap.add_argument("--aia", action="store_true")
    ap.add_argument("--limit", type=int, default=120)
    args = ap.parse_args()
    for url in args.url:
        try:
            if args.kind == "pdf":
                probe_pdf(url, args.grep, args.pages, args.aia, args.limit)
            elif args.kind == "page":
                probe_page(url, args.grep, args.aia, args.limit)
            else:
                probe_xlsx(url, args.grep, args.aia, args.limit)
        except Exception as err:                    # noqa: BLE001 - a probe reports
            log(f"{url}: {type(err).__name__}: {str(err)[:300]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
