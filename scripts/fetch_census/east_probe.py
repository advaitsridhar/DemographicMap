#!/usr/bin/env python3
"""Read-only probes for the eastern European census offices.

Russia, Ukraine, Belarus, Turkey, Georgia, Armenia and Azerbaijan publish their
census tables in ways that have to be looked at before a reader is written:
workbooks in numbered series, PX-Web databases of two generations, and hosts
that answer some networks and not others. This prints what is there -- nothing
is written and nothing is committed; the output is the log.

Subcommands (every argument one whitespace-free token, as the workflow splits
its command on whitespace):

    cdx PREFIX [--match REGEX] [--limit N]
        The Internet Archive's captures of every URL under PREFIX (a host or a
        host/path prefix), newest capture per URL, status 200 only.
    get URL [--wayback TS|latest] [--rows N] [--sheets N] [--grep REGEX]
        Fetch one file and describe it: a workbook's sheets and first rows (or
        the rows matching REGEX), a ZIP's members, a page's links, JSON's
        shape, or the first bytes of anything else.
    post URL --data JSON [--rows N]
        POST a JSON body (a PX-Web query) and describe the answer.
    head URL [URL ...]
        Status, type and length only.
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from typing import Any

from ._shared import http_get

CDX = "https://web.archive.org/cdx/search/cdx"
UA = ("DemographicMap/1.0 (+https://github.com/advaitsridhar/DemographicMap) "
      "python-urllib")


def text(value: Any, width: int) -> str:
    out = "" if value is None else " ".join(str(value).split())
    return out[:width]


def latest(url: str) -> str | None:
    """The newest 200 capture's timestamp for exactly this URL."""
    query = urllib.parse.urlencode({"url": url, "output": "json",
                                    "filter": "statuscode:200",
                                    "fl": "timestamp", "limit": "-1"})
    try:
        rows = json.loads(http_get(f"{CDX}?{query}", cache=False, retries=2,
                                   timeout=90) or "[]")
    except Exception as exc:  # noqa: BLE001
        print(f"  cdx lookup failed: {exc!r}")
        return None
    return rows[-1][0] if len(rows) > 1 else None


def fetch(url: str, wayback: str | None) -> bytes:
    if wayback:
        stamp = latest(url) if wayback == "latest" else wayback
        if not stamp:
            raise SystemExit(f"no capture of {url}")
        url = f"https://web.archive.org/web/{stamp}id_/{url}"
        print(f"  via {url}")
    return http_get(url, binary=True, cache=False, retries=2, timeout=180)


def describe_book(blob: bytes, name: str, args: argparse.Namespace) -> None:
    grep = re.compile(args.grep, re.I) if args.grep else None
    sheets: list[tuple[str, list[list[Any]]]] = []
    if blob[:2] == b"PK":
        import openpyxl
        book = openpyxl.load_workbook(io.BytesIO(blob), read_only=not args.indent,
                                      data_only=True)
        for ws in book.worksheets[:max(args.sheets, 1) if args.indent else None]:
            if args.indent:
                # The first cell's indent and weight, which is how Rosstat
                # and Belstat say which rows sit inside which.
                rows = []
                for r in ws.iter_rows():
                    a = r[0]
                    tag = (f"i{int(a.alignment.indent or 0)}"
                           f"{'b' if a.font and a.font.b else ''}")
                    rows.append([tag] + [c.value for c in r])
                sheets.append((ws.title, rows))
            else:
                sheets.append((ws.title, [list(r) for r in ws.iter_rows(values_only=True)]))
    else:
        import xlrd
        book = xlrd.open_workbook(file_contents=blob)
        for ws in book.sheets():
            sheets.append((ws.name, [ws.row_values(i) for i in range(ws.nrows)]))
    print(f"  {name}: {len(sheets)} sheets: "
          + " | ".join(t for t, _ in sheets[:80]))
    for title, rows in sheets[:args.sheets]:
        width = max((len(r) for r in rows), default=0)
        print(f"  -- sheet {title!r}: {len(rows)} rows x {width} cols")
        shown = 0
        tail = 0
        for i, row in enumerate(rows):
            if i < args.start:
                continue
            line = " | ".join(text(c, args.width) for c in row[:args.cols])
            if grep and grep.search(line):
                tail = args.after
            elif grep and tail <= 0:
                continue
            else:
                tail -= 1
            print(f"    r{i}: {line}")
            shown += 1
            if shown >= args.rows:
                break


def describe(blob: bytes, url: str, args: argparse.Namespace) -> None:
    print(f"  {len(blob):,} bytes, begins {blob[:16]!r}")
    lower = url.lower().split("?")[0]
    if blob[:2] == b"PK" and not lower.endswith((".xlsx", ".xlsm")):
        with zipfile.ZipFile(io.BytesIO(blob)) as zf:
            names = zf.namelist()
            if "[Content_Types].xml" in names:
                describe_book(blob, url, args)
                return
            print(f"  zip, {len(names)} members:")
            for n in names[:args.rows]:
                print(f"    {n} ({zf.getinfo(n).file_size:,})")
            for n in names:
                if n.lower().endswith((".xls", ".xlsx")) and args.sheets:
                    describe_book(zf.read(n), n, args)
                    break
        return
    if blob[:2] == b"PK" or blob[:8] == bytes.fromhex("d0cf11e0a1b11ae1"):
        describe_book(blob, url, args)
        return
    body = blob.decode("utf-8", "replace")
    if body.lstrip().startswith(("{", "[")):
        try:
            data = json.loads(body.lstrip("﻿"))
        except ValueError:
            data = None
        if data is not None:
            print("  json: " + json.dumps(data, ensure_ascii=False)[:args.bytes])
            return
    if args.grep:
        for m in list(re.finditer(args.grep, body, re.I))[:args.rows]:
            s = max(0, m.start() - args.context)
            print("  ~ " + " ".join(body[s:m.end() + args.context].split()))
        return
    links = re.findall(r"""(?is)<a\b[^>]*href\s*=\s*["']([^"']+)["'][^>]*>(.*?)</a>""", body)
    if links:
        match = re.compile(args.links, re.I) if args.links else None
        shown = 0
        for href, label in links:
            label = " ".join(re.sub(r"<[^>]+>", " ", label).split())
            if match and not (match.search(href) or match.search(label)):
                continue
            print(f"  link: {label[:90]!r} -> {urllib.parse.urljoin(url, href)}")
            shown += 1
            if shown >= args.rows:
                break
        print(f"  ({len(links)} links in all)")
    print("  text: " + " ".join(re.sub(r"(?is)<(script|style).*?</\1>|<[^>]+>", " ", body).split())[:args.bytes])


def cmd_cdx(args: argparse.Namespace) -> None:
    params = [("url", args.target), ("matchType", args.match_type),
              ("output", "json"), ("filter", "statuscode:200"),
              ("fl", "original,timestamp,mimetype,length"),
              ("collapse", "urlkey"), ("limit", str(args.cdx_limit))]
    # A second filter is the archive's own regex on a field, which keeps a
    # domain-wide listing to the files that matter before it is sent.
    if args.cdx_filter:
        params.append(("filter", args.cdx_filter))
    url = f"{CDX}?{urllib.parse.urlencode(params)}"
    rows = json.loads(http_get(url, cache=False, retries=2, timeout=180) or "[]")
    match = re.compile(args.match, re.I) if args.match else None
    shown = 0
    for row in rows[1:]:
        original = urllib.parse.unquote(row[0])
        if match and not match.search(original):
            continue
        print(f"  {row[1]} {row[2][:28]:28} {row[3]:>9} {original}")
        shown += 1
        if shown >= args.rows:
            break
    print(f"  {shown} shown of {len(rows) - 1} captured under {args.target}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["cdx", "get", "post", "head"])
    ap.add_argument("target", nargs="+")
    ap.add_argument("--match")
    ap.add_argument("--match-type", default="prefix")
    ap.add_argument("--cdx-limit", type=int, default=20000)
    ap.add_argument("--cdx-filter",
                    help="an extra CDX filter, e.g. original:.*[Tt]om.*xlsx")
    ap.add_argument("--wayback")
    ap.add_argument("--rows", type=int, default=40)
    ap.add_argument("--sheets", type=int, default=2)
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--cols", type=int, default=14)
    ap.add_argument("--width", type=int, default=24)
    ap.add_argument("--grep")
    ap.add_argument("--indent", action="store_true")
    ap.add_argument("--after", type=int, default=0,
                    help="with --grep, also print this many rows after a match")
    ap.add_argument("--links")
    ap.add_argument("--context", type=int, default=160)
    ap.add_argument("--bytes", type=int, default=1500)
    ap.add_argument("--data")
    ap.add_argument("--hosts",
                    help="with a target holding {n}: a range like 1-95 to "
                         "substitute, for an office with one host per region")
    args = ap.parse_args()
    targets = args.target
    if args.hosts:
        low, high = (int(x) for x in args.hosts.split("-"))
        targets = [t.replace("{n}", f"{n:02d}") for t in args.target
                   for n in range(low, high + 1)]
    for target in targets:
        print(f"== {args.cmd} {target}")
        args.target = target
        try:
            if args.cmd == "cdx":
                cmd_cdx(args)
            elif args.cmd == "head":
                req = urllib.request.Request(target, method="HEAD",
                                             headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=60) as resp:
                    print(f"  {resp.status} {resp.headers.get('Content-Type')} "
                          f"{resp.headers.get('Content-Length')}")
            elif args.cmd == "post":
                req = urllib.request.Request(
                    target, data=(args.data or "{}").encode(), method="POST",
                    headers={"User-Agent": UA, "Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=180) as resp:
                    describe(resp.read(), target, args)
            else:
                describe(fetch(target, args.wayback), target, args)
        except urllib.error.HTTPError as exc:
            print(f"  HTTP {exc.code} {exc.reason}: "
                  + " ".join(exc.read()[:300].decode("utf-8", "replace").split()))
        except SystemExit as exc:
            print(f"  stopped: {exc}")
        except Exception as exc:  # noqa: BLE001 - a probe reports, it does not stop
            print(f"  failed: {exc!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
