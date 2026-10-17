#!/usr/bin/env python3
"""Uganda: what the 2002 census's published tabulations hold, read from the
Internet Archive's copy of the Bureau's archive of them.

The Uganda Bureau of Statistics publishes the 2002 Population and Housing
Census's tabulations as one ZIP of 67 PDF tables
(``10_20212002_census_tabulations_pdf.zip``). The Bureau's host fails
certificate checks from the runner, so the Internet Archive's capture is read
(its ``id_`` form returns the original bytes).

``--titles`` prints each table's page count and the first lines of its first
page, so that what each table tabulates, and at which level, is known before
anything is written; ``--member NAME --pages N`` prints a table's first pages.
Nothing is written; the output is the log.

Usage:
    python -m scripts.fetch_census.uganda_2002 --titles
    python -m scripts.fetch_census.uganda_2002 --member centableB3.pdf --pages 3
"""

from __future__ import annotations

import argparse
import hashlib
import io
import zipfile

from ._shared import http_get, log

ZIP = ("https://web.archive.org/web/20211116120534id_/https://www.ubos.org/wp-content/"
       "uploads/publications/10_20212002_census_tabulations_pdf.zip")


def members() -> dict[str, bytes]:
    blob = http_get(ZIP, binary=True, cache=False, timeout=600)
    log(f"  read {ZIP}: {len(blob):,} bytes, sha256 {hashlib.sha256(blob).hexdigest()}")
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        return {n.rsplit("/", 1)[-1]: zf.read(n) for n in zf.namelist()
                if n.lower().endswith(".pdf")}


def page_texts(blob: bytes, pages: int) -> list[str]:
    from pypdf import PdfReader                    # noqa: PLC0415
    reader = PdfReader(io.BytesIO(blob))
    return [(p.extract_text() or "") for p in reader.pages[:pages]] + [f"[{len(reader.pages)}]"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--titles", action="store_true")
    ap.add_argument("--member", default="")
    ap.add_argument("--pages", type=int, default=2)
    ap.add_argument("--lines", type=int, default=9)
    ap.add_argument("--run", default="", help="a label that tells two dispatches apart; ignored")
    args = ap.parse_args()
    tables = members()
    if args.titles:
        for name in sorted(tables, key=lambda n: (len(n), n)):
            texts = page_texts(tables[name], 1)
            lines = [" ".join(x.split()) for x in texts[0].splitlines() if x.strip()]
            words = texts[0].lower()
            log(f"== {name} {texts[-1]} pages; religion {words.count('religio')}, ethnic "
                f"{words.count('ethnic') + words.count('tribe')}, county {words.count('county')}, "
                f"district {words.count('district')}")
            for line in lines[:args.lines]:
                log(f"    {line[:160]}")
    if args.member:
        texts = page_texts(tables[args.member], args.pages)
        log(f"== {args.member} ({texts[-1]} pages)")
        for i, text in enumerate(texts[:-1], 1):
            log(f"--- page {i}")
            for line in text.splitlines():
                if line.strip():
                    log(f"    {' '.join(line.split())[:200]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
