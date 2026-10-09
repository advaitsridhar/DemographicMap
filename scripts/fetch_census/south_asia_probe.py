#!/usr/bin/env python3
"""South Asia reconnaissance: what each office serves, before a reader.

Read-only; nothing is written and the output is the log. Each subcommand
answers one question and prints only what decides it. Every fetch can take
``--aia``, which completes a certificate chain the server sends one link short
(censusindia.gov.in, bbs.gov.bd) from the certificate's own AIA extension and
then verifies normally -- see scripts/probe_tls.py. Verification is never
switched off.

* ``get URL...`` -- status, type and size of each body; with ``--links`` the
  links whose href or text match, with ``--grep`` the text lines that match.
* ``heads TEMPLATE --values a,b,c`` -- the same URL shape with each value put
  in place of ``{}``: which answer, and how big. A guessed URL that 404s and a
  table that was never published are the same observation, so the run asks
  for every candidate rather than one.
* ``nada BASE --keyword K`` -- a NADA catalogue's search, one line per study
  (id, idno, year, title).
* ``nadafiles BASE ID...`` -- a study's downloadable files, read from its
  related-materials page.
* ``xls URL`` -- a workbook's sheets and their first rows.
* ``pdf URL`` -- page count, and the text of chosen pages or of the pages
  matching ``--grep``.
* ``cdx PATTERN`` -- the Internet Archive's captures of a URL pattern.
* ``wd NAME...`` -- Wikidata items by name with their point and parent: a
  locator for binding, never a figure.

Usage:
    python -m scripts.fetch_census.south_asia_probe get https://example.org --links xls,pdf
    python -m scripts.fetch_census.south_asia_probe heads https://x/table_{}.pdf --values 1,2,3
    python -m scripts.fetch_census.south_asia_probe nada https://censusindia.gov.in/nada --keyword C-13 --aia
"""

from __future__ import annotations

import argparse
import html
import io
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import USER_AGENT                      # noqa: E402

TIMEOUT = 120
_OPENERS: dict[str, Any] = {}


def opener_for(url: str, aia: bool):
    if not aia:
        return urllib.request.urlopen
    host = urllib.parse.urlsplit(url).hostname or ""
    if host not in _OPENERS:
        from probe_tls import verified_opener      # noqa: PLC0415
        try:
            _OPENERS[host] = verified_opener(host).open
        except Exception as err:                   # noqa: BLE001 -- reported
            print(f"    aia: could not complete the chain for {host}: "
                  f"{type(err).__name__}: {str(err)[:160]}")
            _OPENERS[host] = urllib.request.urlopen
    return _OPENERS[host]


def fetch(url: str, *, aia: bool = False, limit: int | None = None,
          method: str = "GET", accept: str | None = None,
          data: bytes | None = None,
          extra: dict[str, str] | None = None) -> tuple[int, dict[str, str], bytes, str]:
    """(status, headers, body, final url); a failure is reported, not raised."""
    headers = {"User-Agent": USER_AGENT}
    if accept:
        headers["Accept"] = accept
    headers.update(extra or {})
    req = urllib.request.Request(url, headers=headers, method=method, data=data)
    try:
        with opener_for(url, aia)(req, timeout=TIMEOUT) as fh:
            body = fh.read(limit) if limit else fh.read()
            return fh.status, dict(fh.headers.items()), body, fh.geturl()
    except urllib.error.HTTPError as err:
        try:
            body = err.read()[:4000]
        except Exception:                          # noqa: BLE001
            body = b""
        return err.code, dict(err.headers.items()) if err.headers else {}, body, url
    except Exception as err:                       # noqa: BLE001 -- reported
        return -1, {"error": f"{type(err).__name__}: {str(err)[:200]}"}, b"", url


def text_of(body: bytes, charset: str = "utf-8") -> str:
    return body.decode(charset, "replace")


LINK = re.compile(r"""<a\b[^>]*?href\s*=\s*["']([^"']+)["'][^>]*>(.*?)</a>""", re.I | re.S)
TAG = re.compile(r"<[^>]+>")


def links(page: str, base: str) -> list[tuple[str, str]]:
    out = []
    for href, label in LINK.findall(page):
        label = html.unescape(TAG.sub(" ", label))
        out.append((urllib.parse.urljoin(base, html.unescape(href)),
                    " ".join(label.split())))
    return out


def plain(page: str) -> list[str]:
    page = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", page)
    page = re.sub(r"(?i)<(br|/p|/tr|/li|/h\d|/div|/td|/th)\b[^>]*>", "\n", page)
    text = html.unescape(TAG.sub(" ", page))
    return [" ".join(line.split()) for line in text.splitlines() if line.strip()]


def describe(url: str, status: int, headers: dict[str, str], body: bytes) -> None:
    kind = headers.get("Content-Type") or headers.get("content-type") or ""
    size = headers.get("Content-Length") or headers.get("content-length") or len(body)
    err = headers.get("error")
    print(f"  {status} {kind[:40]} {size} {url}" + (f"  !! {err}" if err else ""))


def cmd_get(args: argparse.Namespace) -> None:
    for url in args.urls:
        status, headers, body, final = fetch(url, aia=args.aia, accept=args.accept)
        print(f"\n== GET {url}")
        if final != url:
            print(f"   (redirected to {final})")
        describe(url, status, headers, body)
        if not body:
            continue
        page = text_of(body, args.charset)
        if args.links is not None:
            pattern = re.compile(args.links, re.I) if args.links else None
            seen = set()
            shown = 0
            for href, label in links(page, final):
                if pattern and not (pattern.search(href) or pattern.search(label)):
                    continue
                if href in seen:
                    continue
                seen.add(href)
                print(f"    {label[:70]!r} -> {href}")
                shown += 1
                if shown >= args.rows:
                    print("    ...")
                    break
        if args.grep:
            pattern = re.compile(args.grep, re.I)
            lines = plain(page) if "<" in page[:2000] else page.splitlines()
            shown = 0
            for i, line in enumerate(lines):
                if pattern.search(line):
                    lo, hi = max(0, i - args.context), min(len(lines), i + args.context + 1)
                    for j in range(lo, hi):
                        print(f"    {'>' if j == i else ' '} {lines[j][:args.width]}")
                    if args.context:
                        print("    --")
                    shown += 1
                    if shown >= args.rows:
                        print("    ...")
                        break
        if args.chars:
            print("    " + page[:args.chars].replace("\n", "\n    "))


def cmd_heads(args: argparse.Namespace) -> None:
    values = [v for v in args.values.split(",") if v]
    print(f"== {len(values)} candidate(s) of {args.template}")
    for value in values:
        url = args.template.replace("{}", value)
        status, headers, body, _ = fetch(url, aia=args.aia, limit=args.peek or 2048)
        kind = (headers.get("Content-Type") or headers.get("content-type") or "")[:30]
        size = headers.get("Content-Length") or headers.get("content-length") or "?"
        note = ""
        if status == 200 and args.peek and body[:4] == b"%PDF":
            note = " pdf"
        elif status == 200 and b"<html" in body[:600].lower():
            title = re.search(rb"<title>(.*?)</title>", body, re.I | re.S)
            note = f" html title={title.group(1)[:60].decode('utf-8', 'replace').strip()!r}" if title else " html"
        err = headers.get("error")
        print(f"  {status} {size:>10} {kind:<30} {value}{note}" + (f" !! {err}" if err else ""))


def cmd_nada(args: argparse.Namespace) -> None:
    root = args.base.rstrip("/")
    for keyword in args.keyword.split(","):
        page = 1
        shown = 0
        while shown < args.limit and page <= args.pages:
            url = (f"{root}/index.php/api/catalog/search?"
                   + urllib.parse.urlencode({"sk": keyword, "ps": min(100, args.limit),
                                             "page": page}))
            status, headers, body, _ = fetch(url, aia=args.aia, accept="application/json")
            print(f"\n== NADA {keyword!r} page {page}: {status}"
                  + (f" !! {headers.get('error')}" if headers.get("error") else ""))
            if status != 200:
                print("    " + text_of(body)[:400])
                break
            try:
                payload = json.loads(text_of(body))
            except ValueError:
                print("    not JSON: " + text_of(body)[:300])
                break
            result = payload.get("result") or payload
            rows = result.get("rows") or []
            if page == 1:
                print(f"    found {result.get('found')} total {result.get('total')}")
                if rows and args.raw:
                    print("    " + json.dumps(rows[0])[:1500])
            if not rows:
                break
            keep = re.compile(args.match, re.I) if args.match else None
            for row in rows:
                title = f"{row.get('idno')} {row.get('title')}"
                if keep and not keep.search(title):
                    continue
                print(f"    id={row.get('id')} idno={row.get('idno')} "
                      f"{row.get('year_start') or ''} {str(row.get('title'))[:110]}")
                shown += 1
            page += 1
            if len(rows) < min(100, args.limit) or page > args.pages:
                break


def cmd_nadafiles(args: argparse.Namespace) -> None:
    root = args.base.rstrip("/")
    for study in args.ids:
        for path in (f"{root}/index.php/catalog/{study}/related-materials",
                     f"{root}/index.php/catalog/{study}/get-microdata",
                     f"{root}/index.php/api/catalog/{study}/resources"):
            status, headers, body, final = fetch(path, aia=args.aia)
            print(f"\n== {study}: {status} {path}"
                  + (f" !! {headers.get('error')}" if headers.get("error") else ""))
            if status != 200:
                continue
            page = text_of(body)
            if path.endswith("/resources"):
                print("    " + page[:args.chars])
                continue
            found = [(h, label) for h, label in links(page, final)
                     if "/download/" in h or re.search(r"\.(xlsx?|pdf|zip|csv)$", h, re.I)]
            for href, label in found[:args.rows]:
                print(f"    {label[:60]!r} -> {href}")
            if not found:
                print("    no download links")


def cmd_xls(args: argparse.Namespace) -> None:
    for url in args.urls:
        status, headers, body, _ = fetch(url, aia=args.aia)
        print(f"\n== {url}")
        describe(url, status, headers, body)
        if status != 200 or not body:
            continue
        rows_of: list[tuple[str, int, int, list[list[Any]]]] = []
        if body[:2] == b"PK":
            import openpyxl                         # noqa: PLC0415
            book = openpyxl.load_workbook(io.BytesIO(body), read_only=True, data_only=True)
            for sheet in book.worksheets[:args.sheets]:
                grid = []
                for i, row in enumerate(sheet.iter_rows(values_only=True), 1):
                    if i < args.start:
                        continue
                    grid.append(list(row))
                    if len(grid) >= args.rows:
                        break
                rows_of.append((sheet.title, sheet.max_row or 0, sheet.max_column or 0, grid))
            names = book.sheetnames
        else:
            import xlrd                             # noqa: PLC0415
            book = xlrd.open_workbook(file_contents=body)
            names = book.sheet_names()
            for sheet in book.sheets()[:args.sheets]:
                grid = [sheet.row_values(i) for i in range(args.start - 1,
                                                           min(sheet.nrows, args.start - 1 + args.rows))]
                rows_of.append((sheet.name, sheet.nrows, sheet.ncols, grid))
        print(f"    {len(names)} sheet(s): {names[:60]}")
        for title, nrows, ncols, grid in rows_of:
            print(f"  -- sheet {title!r} {nrows}x{ncols}")
            for row in grid:
                cells = ["" if c is None else str(c).replace("\n", " ")[:args.width]
                         for c in row[:args.cols]]
                print("    | " + " | ".join(cells))


def cmd_pdf(args: argparse.Namespace) -> None:
    status, headers, body, _ = fetch(args.url, aia=args.aia)
    print(f"== {args.url}")
    describe(args.url, status, headers, body)
    if status != 200 or body[:4] != b"%PDF":
        print("    not a PDF: " + text_of(body[:300]))
        return
    import pdfplumber                               # noqa: PLC0415
    with pdfplumber.open(io.BytesIO(body)) as pdf:
        print(f"    {len(pdf.pages)} pages")
        wanted: list[int] = []
        for part in (args.pages or "").split(","):
            if "-" in part:
                lo, hi = part.split("-")
                wanted.extend(range(int(lo), int(hi) + 1))
            elif part:
                wanted.append(int(part))
        pattern = re.compile(args.grep, re.I) if args.grep else None
        hits = 0
        for number, page in enumerate(pdf.pages, 1):
            if wanted and number not in wanted:
                continue
            if not wanted and not pattern:
                break
            if pattern and not wanted and hits >= args.max_pages:
                break
            text = page.extract_text(layout=args.layout) or ""
            if pattern and not pattern.search(text):
                continue
            hits += 1
            print(f"\n  -- page {number}")
            lines = [ln.rstrip() for ln in text.splitlines() if ln.strip()]
            if pattern and not wanted and args.context >= 0:
                keep = set()
                for i, ln in enumerate(lines):
                    if pattern.search(ln):
                        keep.update(range(max(0, i - args.context),
                                          min(len(lines), i + args.context + 1)))
                lines = [lines[i] for i in sorted(keep)]
            for ln in lines[:args.lines]:
                print("    " + ln[:args.width])


def cmd_pdftitles(args: argparse.Namespace) -> None:
    """The opening lines of each PDF's first pages: which table a file is."""
    import pdfplumber                               # noqa: PLC0415
    for value in [v for v in args.values.split(",") if v] or [""]:
        url = args.template.replace("{}", value)
        status, headers, body, _ = fetch(url, aia=args.aia)
        print(f"\n== {url}")
        if status != 200 or body[:4] != b"%PDF":
            describe(url, status, headers, body)
            continue
        try:
            with pdfplumber.open(io.BytesIO(body)) as pdf:
                print(f"    {len(pdf.pages)} pages, {len(body):,} bytes")
                for number in range(min(args.pages, len(pdf.pages))):
                    text = pdf.pages[number].extract_text(layout=args.layout) or ""
                    lines = [ln.rstrip() for ln in text.splitlines() if ln.strip()]
                    print(f"  -- page {number + 1}")
                    for ln in lines[:args.lines]:
                        print("    " + ln[:args.width])
        except Exception as err:                   # noqa: BLE001 -- reported
            print(f"    unreadable: {type(err).__name__}: {err}")


def cmd_rows(args: argparse.Namespace) -> None:
    """A PDF's words grouped into rows by their vertical position, with x.

    What a word-box table reader sees: each row as ``text@x0`` words, so a
    label printed a point above its figures, or a figure split in two, shows.
    """
    import pdfplumber                               # noqa: PLC0415
    status, headers, body, _ = fetch(args.url, aia=args.aia)
    print(f"== {args.url}")
    describe(args.url, status, headers, body)
    if status != 200 or body[:4] != b"%PDF":
        return
    wanted = {int(p) for p in args.pages.split(",") if p and p != "all"}
    pattern = re.compile(args.grep, re.I) if args.grep else None
    # --find picks the pages by their text instead of by number: the first
    # --max-pages pages whose extracted text matches, each shown whole (or
    # filtered by --grep).
    find = re.compile(args.find) if args.find else None
    found = 0
    with pdfplumber.open(io.BytesIO(body)) as pdf:
        print(f"    {len(pdf.pages)} pages")
        for number, page in enumerate(pdf.pages, 1):
            if wanted and number not in wanted:
                continue
            if find:
                if found >= args.max_pages:
                    break
                if not find.search(page.extract_text() or ""):
                    continue
                found += 1
            words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
            rows: list[tuple[float, list]] = []
            for word in sorted(words, key=lambda w: (round(w["top"], 1), w["x0"])):
                top = round(word["top"], 1)
                if rows and abs(rows[-1][0] - top) <= args.tolerance:
                    rows[-1][1].append(word)
                else:
                    rows.append((top, [word]))
            print(f"  -- page {number}: {len(rows)} rows")
            shown = 0
            for top, row in rows:
                line = " ".join(w["text"] for w in sorted(row, key=lambda w: w["x0"]))
                if pattern and not pattern.search(line):
                    continue
                cells = " ".join(f"{w['text']}@{w['x0']:.0f}-{w['x1']:.0f}"
                                 for w in sorted(row, key=lambda w: w["x0"]))
                print(f"    y={top:6.1f} {cells[:args.width]}")
                shown += 1
                if shown >= args.lines:
                    break


def cmd_cdx(args: argparse.Namespace) -> None:
    url = ("https://web.archive.org/cdx/search/cdx?"
           + urllib.parse.urlencode({"url": args.pattern, "output": "json",
                                     "limit": args.limit, "fl": "timestamp,original,statuscode,mimetype,length",
                                     "collapse": "urlkey"}))
    status, headers, body, _ = fetch(url)
    print(f"== CDX {args.pattern}: {status}" + (f" !! {headers.get('error')}" if headers.get("error") else ""))
    if status != 200:
        print("    " + text_of(body)[:300])
        return
    try:
        rows = json.loads(text_of(body) or "[]")
    except ValueError:
        print("    " + text_of(body)[:300])
        return
    pattern = re.compile(args.match, re.I) if args.match else None
    shown = 0
    for row in rows[1:]:
        if pattern and not pattern.search(row[1]):
            continue
        print("    " + " ".join(str(c) for c in row))
        shown += 1
        if shown >= args.rows:
            print("    ...")
            break
    print(f"    {len(rows) - 1} capture(s), {shown} shown")


WIKIDATA = "https://www.wikidata.org/w/api.php"


def cmd_wd(args: argparse.Namespace) -> None:
    """Wikidata items by name: id, label, description, point and admin parent.

    A locator only -- where a place is, so that a polygon it falls in can be
    named -- never a figure. ``_`` in a name stands for a space, the command
    line being split on whitespace.
    """
    for name in args.names:
        text = name.replace("_", " ")
        url = WIKIDATA + "?" + urllib.parse.urlencode({
            "action": "wbsearchentities", "search": text, "language": args.lang,
            "format": "json", "limit": args.limit, "type": "item"})
        status, headers, body, _ = fetch(url, accept="application/json")
        print(f"\n== {text!r}: {status}")
        if status != 200:
            continue
        hits = json.loads(text_of(body)).get("search") or []
        if not hits:
            print("    no item")
            continue
        ids = [h["id"] for h in hits]
        status, _h, body, _ = fetch(WIKIDATA + "?" + urllib.parse.urlencode({
            "action": "wbgetentities", "ids": "|".join(ids), "props": "claims|labels",
            "languages": "en", "format": "json"}), accept="application/json")
        entities = json.loads(text_of(body)).get("entities", {}) if status == 200 else {}
        parents: dict[str, str] = {}
        for hit in hits:
            claims = entities.get(hit["id"], {}).get("claims", {})
            point = ""
            for claim in claims.get("P625", [])[:1]:
                value = claim.get("mainsnak", {}).get("datavalue", {}).get("value", {})
                point = f"{value.get('latitude', 0):.4f},{value.get('longitude', 0):.4f}"
            within = [c.get("mainsnak", {}).get("datavalue", {}).get("value", {}).get("id")
                      for c in claims.get("P131", [])]
            kinds = [c.get("mainsnak", {}).get("datavalue", {}).get("value", {}).get("id")
                     for c in claims.get("P31", [])]
            parents[hit["id"]] = ",".join(w for w in within if w)
            print(f"    {hit['id']} {hit.get('label')!r} -- {str(hit.get('description', ''))[:70]!r} "
                  f"point={point or '-'} P131={parents[hit['id']] or '-'} P31={','.join(k for k in kinds if k)[:60]}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("get")
    g.add_argument("urls", nargs="+")
    g.add_argument("--links", nargs="?", const="", default=None)
    g.add_argument("--grep", default="")
    g.add_argument("--context", type=int, default=0)
    g.add_argument("--rows", type=int, default=80)
    g.add_argument("--width", type=int, default=220)
    g.add_argument("--chars", type=int, default=0)
    g.add_argument("--charset", default="utf-8")
    g.add_argument("--accept", default=None)
    g.add_argument("--aia", action="store_true")

    h = sub.add_parser("heads")
    h.add_argument("template")
    h.add_argument("--values", required=True)
    h.add_argument("--peek", type=int, default=2048)
    h.add_argument("--aia", action="store_true")

    n = sub.add_parser("nada")
    n.add_argument("base")
    n.add_argument("--keyword", required=True)
    n.add_argument("--limit", type=int, default=100)
    n.add_argument("--raw", action="store_true")
    n.add_argument("--match", default="", help="print only rows whose idno or title match")
    n.add_argument("--pages", type=int, default=30, help="result pages to walk")
    n.add_argument("--aia", action="store_true")

    f = sub.add_parser("nadafiles")
    f.add_argument("base")
    f.add_argument("ids", nargs="+")
    f.add_argument("--rows", type=int, default=40)
    f.add_argument("--chars", type=int, default=1500)
    f.add_argument("--aia", action="store_true")

    x = sub.add_parser("xls")
    x.add_argument("urls", nargs="+")
    x.add_argument("--sheets", type=int, default=3)
    x.add_argument("--rows", type=int, default=12)
    x.add_argument("--start", type=int, default=1)
    x.add_argument("--cols", type=int, default=16)
    x.add_argument("--width", type=int, default=16)
    x.add_argument("--aia", action="store_true")

    p = sub.add_parser("pdf")
    p.add_argument("url")
    p.add_argument("--pages", default="")
    p.add_argument("--grep", default="")
    p.add_argument("--context", type=int, default=-1)
    p.add_argument("--max-pages", type=int, default=6)
    p.add_argument("--lines", type=int, default=80)
    p.add_argument("--width", type=int, default=200)
    p.add_argument("--layout", action="store_true")
    p.add_argument("--aia", action="store_true")

    t = sub.add_parser("pdftitles")
    t.add_argument("template")
    t.add_argument("--values", default="")
    t.add_argument("--pages", type=int, default=1)
    t.add_argument("--lines", type=int, default=14)
    t.add_argument("--width", type=int, default=180)
    t.add_argument("--layout", action="store_true")
    t.add_argument("--aia", action="store_true")

    w = sub.add_parser("rows")
    w.add_argument("url")
    w.add_argument("--pages", default="1")
    w.add_argument("--grep", default="")
    w.add_argument("--lines", type=int, default=80)
    w.add_argument("--width", type=int, default=400)
    w.add_argument("--tolerance", type=float, default=2.0)
    w.add_argument("--find", default="", help="pick pages whose text matches")
    w.add_argument("--max-pages", type=int, default=4)
    w.add_argument("--aia", action="store_true")

    c = sub.add_parser("cdx")
    c.add_argument("pattern")
    c.add_argument("--match", default="")
    c.add_argument("--limit", type=int, default=5000)
    c.add_argument("--rows", type=int, default=80)

    d = sub.add_parser("wd")
    d.add_argument("names", nargs="+")
    d.add_argument("--lang", default="en")
    d.add_argument("--limit", type=int, default=4)

    args = ap.parse_args()
    {"get": cmd_get, "heads": cmd_heads, "nada": cmd_nada, "nadafiles": cmd_nadafiles,
     "xls": cmd_xls, "pdf": cmd_pdf, "pdftitles": cmd_pdftitles,
     "rows": cmd_rows, "cdx": cmd_cdx, "wd": cmd_wd}[args.cmd](args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
