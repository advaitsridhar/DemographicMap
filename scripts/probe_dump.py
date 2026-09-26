#!/usr/bin/env python3
"""Print a source whole: every row of a page's tables, a workbook's sheets, a PDF's pages.

The other probes answer "what is there" -- links, sheet names, the pages
mentioning a word. Writing a parser needs the next thing: the rows
themselves, with every cell, so the reader is written against the layout the
office actually printed rather than a sample of it. Nothing is written and
nothing is committed; the output is the log.

* ``--html``: every <table> row on the page, cells joined by " | ".
* ``--xlsx`` (also .xls): every row of each sheet, up to ``--rows``.
* ``--pdf``: the text of the pages given (``--pages 3-7,12``), laid out by
  pdfplumber with its word positions kept (``--layout``), or the pages that
  mention ``--terms`` when no pages are given.
* ``--wayback TS``: fetch each URL from the Internet Archive's capture at that
  timestamp, raw (``id_``), for an office whose own host refuses the runner.

Usage:
    python -m scripts.probe_dump --html https://example.org/table.aspx
    python -m scripts.probe_dump --xlsx https://example.org/census.xlsx --rows 60
    python -m scripts.probe_dump --pdf https://example.org/report.pdf --terms religion,ethnic
    python -m scripts.probe_dump --pdf https://example.org/report.pdf --pages 40-44 --layout
"""

from __future__ import annotations

import argparse
import html as htmllib
import io
import re
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import USER_AGENT  # noqa: E402

TIMEOUT = 120


def fetch(url: str, wayback: str = "") -> bytes:
    if wayback:
        url = f"https://web.archive.org/web/{wayback}id_/{url}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return resp.read()


def text_of(fragment: str) -> str:
    return re.sub(r"\s+", " ", htmllib.unescape(re.sub(r"(?s)<[^>]+>", " ", fragment))).strip()


def dump_html(body: bytes, limit: int) -> None:
    page = body.decode("utf-8", "replace")
    tables = re.findall(r"(?is)<table\b.*?</table>", page)
    print(f"  {len(page):,} characters, {len(tables)} table(s)")
    title = re.search(r"(?is)<title>(.*?)</title>", page)
    if title:
        print(f"  title: {text_of(title.group(1))}")
    for t, table in enumerate(tables):
        rows = re.findall(r"(?is)<tr\b.*?</tr>", table)
        print(f"  -- table {t}: {len(rows)} rows")
        for row in rows[:limit]:
            cells = [text_of(c) for c in re.findall(r"(?is)<t[dh]\b.*?</t[dh]>", row)]
            print("    " + " | ".join(cells))
    if not tables:
        print(text_of(page)[:4000])


def dump_book(body: bytes, limit: int, sheets: list[str]) -> None:
    if body[:4] == b"PK\x03\x04":
        import openpyxl
        book = openpyxl.load_workbook(io.BytesIO(body), read_only=True, data_only=True)
        named = [(n, (list(r) for r in book[n].iter_rows(values_only=True)))
                 for n in book.sheetnames]
    else:
        import xlrd
        book = xlrd.open_workbook(file_contents=body)
        named = [(s.name, (s.row_values(i) for i in range(s.nrows))) for s in book.sheets()]
    print(f"  sheets: {', '.join(n for n, _ in named)}")
    for name, rows in named:
        if sheets and not any(s.lower() in name.lower() for s in sheets):
            continue
        print(f"  -- sheet {name!r}")
        for i, row in enumerate(rows):
            if i >= limit:
                print("    ...")
                break
            cells = ["" if v is None else (f"{v:g}" if isinstance(v, float) else str(v))
                     for v in row]
            while cells and not cells[-1]:
                cells.pop()
            if cells:
                print(f"    {i}: " + " | ".join(c.strip() for c in cells))


def pages_of(spec: str, count: int) -> list[int]:
    out: list[int] = []
    for part in spec.split(","):
        if "-" in part:
            a, b = part.split("-")
            out.extend(range(int(a), int(b) + 1))
        elif part.strip():
            out.append(int(part))
    return [p for p in out if 1 <= p <= count]


def dump_pdf(body: bytes, pages: str, terms: str, layout: bool, contents: int) -> None:
    import pdfplumber
    with pdfplumber.open(io.BytesIO(body)) as pdf:
        count = len(pdf.pages)
        print(f"  {count} pages")
        if contents:
            for p in range(min(contents, count)):
                text = pdf.pages[p].extract_text() or ""
                print(f"  == page {p + 1} ==")
                print(text)
        if terms and not pages:
            words = [t.strip().lower() for t in terms.split(",") if t.strip()]
            for p in range(count):
                text = (pdf.pages[p].extract_text() or "").lower()
                found = [w for w in words if w in text]
                if found:
                    first = next((ln for ln in text.splitlines() if ln.strip()), "")
                    print(f"  page {p + 1}: {', '.join(found)} :: {first[:120]}")
        for p in pages_of(pages, count):
            page = pdf.pages[p - 1]
            print(f"  == page {p} ==")
            print(page.extract_text(layout=layout) or "")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("url", nargs="+")
    kind = ap.add_mutually_exclusive_group(required=True)
    kind.add_argument("--html", action="store_true")
    kind.add_argument("--xlsx", action="store_true")
    kind.add_argument("--pdf", action="store_true")
    ap.add_argument("--rows", type=int, default=400)
    ap.add_argument("--sheet", action="append", default=[])
    ap.add_argument("--pages", default="")
    ap.add_argument("--terms", default="")
    ap.add_argument("--contents", type=int, default=0,
                    help="with --pdf, print the first N pages whole")
    ap.add_argument("--layout", action="store_true")
    ap.add_argument("--wayback", default="")
    args = ap.parse_args()
    for url in args.url:
        print(f"source: {url}" + (f" (Internet Archive {args.wayback})" if args.wayback else ""))
        try:
            body = fetch(url, args.wayback)
        except Exception as err:                      # noqa: BLE001
            print(f"  unreachable: {type(err).__name__}: {str(err)[:300]}")
            continue
        print(f"  {len(body):,} bytes")
        try:
            if args.html:
                dump_html(body, args.rows)
            elif args.xlsx:
                dump_book(body, args.rows, args.sheet)
            else:
                dump_pdf(body, args.pages, args.terms, args.layout, args.contents)
        except Exception as err:                      # noqa: BLE001
            print(f"  unreadable: {type(err).__name__}: {str(err)[:300]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
