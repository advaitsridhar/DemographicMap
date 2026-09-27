#!/usr/bin/env python3
"""Probe the Balkan and south-east European statistics offices, several at once.

Each argument is one probe, ``mode:url`` with optional ``~~`` parts after it:

    head:URL                     status, type and size only
    text:URL[~~N]                the first N characters of the body, tags stripped
    grep:URL~~REGEX[~~N]         up to N matches of REGEX in the raw body
    links:URL~~REGEX[~~N]        up to N links (href and text) matching REGEX
    xls:URL[~~ROWS[~~SHEETS]]    a workbook's sheets, sizes and first rows
    xlsrow:URL~~SHEET~~REGEX[~~N]  rows of one sheet whose text matches REGEX
    zip:URL                      a zip archive's members
    px:URL                       a PxWeb API node: its children, or a table's variables
    pxtree:URL~~REGEX~~DEPTH~~N  walk a PxWeb tree, printing tables whose title matches
    pxq:URL~~B64JSON             POST a PxWeb query (base64 of the JSON body)
    cdx:URLPREFIX[~~N]           Internet Archive captures under a URL prefix
    pdf:URL~~REGEX[~~N]          lines of a PDF's text matching REGEX

The commands are split on whitespace by the workflow, so no part may hold a
space: a regex uses ``\\s`` instead. Read-only; the output is the log.

Usage:
    python -m scripts.fetch_census.balkans_probe head:https://example.org/a.xlsx
"""

from __future__ import annotations

import base64
import html
import io
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import USER_AGENT  # noqa: E402

TIMEOUT = 60
MODES = ("head", "text", "grep", "links", "xls", "xlsrow", "zip", "px", "pxtree", "pxq", "cdx", "pdf")


def uri(url: str) -> str:
    return urllib.parse.quote(url, safe="%/:=&?~#+!$,;'@()*[]")


def fetch(url: str, data: bytes | None = None, headers: dict | None = None,
          timeout: int = TIMEOUT) -> tuple[int, dict, bytes]:
    hdrs = {"User-Agent": USER_AGENT, "Accept": "*/*"}
    hdrs.update(headers or {})
    req = urllib.request.Request(uri(url), data=data, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            if resp.headers.get("Content-Encoding") == "gzip":
                import gzip
                body = gzip.decompress(body)
            return resp.status, dict(resp.headers), body
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers or {}), exc.read() or b""


def decode(body: bytes, headers: dict) -> str:
    ctype = headers.get("Content-Type", "") or ""
    m = re.search(r"charset=([\w-]+)", ctype)
    for enc in ([m.group(1)] if m else []) + ["utf-8", "cp1250", "cp1251", "latin-1"]:
        try:
            return body.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return body.decode("utf-8", "replace")


def strip(text: str) -> str:
    text = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def say(line: str) -> None:
    print(line, flush=True)


def summary(url: str, status: int, headers: dict, body: bytes) -> None:
    say(f"  HTTP {status} {headers.get('Content-Type', '?')} {len(body):,} bytes"
        + (f" disposition={headers.get('Content-Disposition')}" if headers.get("Content-Disposition") else ""))


def rows_of(blob: bytes) -> dict[str, list[list[str]]]:
    out: dict[str, list[list[str]]] = {}
    if blob[:2] == b"PK":
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(blob), read_only=True, data_only=True)
        for ws in wb.worksheets:
            out[ws.title] = [["" if v is None else str(v) for v in row]
                             for row in ws.iter_rows(values_only=True)]
    else:
        import xlrd
        wb = xlrd.open_workbook(file_contents=blob)
        for sh in wb.sheets():
            out[sh.name] = [[str(sh.cell_value(r, c)) for c in range(sh.ncols)]
                            for r in range(sh.nrows)]
    return out


def show_row(row: list[str], width: int = 28, cols: int = 16) -> str:
    cells = [c.strip().replace("\n", " ")[:width] for c in row[:cols]]
    while cells and not cells[-1]:
        cells.pop()
    return " | ".join(cells)


def probe(arg: str) -> None:
    mode, _, rest = arg.partition(":")
    if mode not in MODES:
        say(f"?? unknown mode in {arg!r}")
        return
    parts = rest.split("~~")
    url = parts[0]
    extra = parts[1:]
    say(f"== {mode} {url} {' '.join(extra)}")
    try:
        if mode == "cdx":
            n = int(extra[0]) if extra else 60
            q = ("https://web.archive.org/cdx/search/cdx?url=" + urllib.parse.quote(url, safe="")
                 + "&matchType=prefix&filter=statuscode:200&collapse=urlkey&limit=" + str(n * 4))
            status, headers, body = fetch(q, timeout=120)
            lines = decode(body, headers).splitlines()
            say(f"  HTTP {status}: {len(lines)} captures")
            for line in lines[:n]:
                f = line.split(" ")
                if len(f) >= 7:
                    say(f"  {f[1]} {f[3]} {f[6]} {f[2]}")
            return
        if mode == "pxtree":
            rx = re.compile(extra[0], re.I) if extra and extra[0] else None
            depth = int(extra[1]) if len(extra) > 1 else 4
            limit = int(extra[2]) if len(extra) > 2 else 150
            shown = [0]

            def walk(path: str, level: int) -> None:
                if shown[0] >= limit:
                    return
                status, headers, body = fetch(path)
                if status != 200:
                    say(f"  {path} HTTP {status}")
                    return
                try:
                    nodes = json.loads(decode(body, headers).lstrip("﻿"))
                except ValueError:
                    say(f"  {path}: not JSON")
                    return
                if not isinstance(nodes, list):
                    return
                for node in nodes:
                    nid = node.get("id") or node.get("dbid")
                    text = node.get("text", "")
                    child = path.rstrip("/") + "/" + urllib.parse.quote(str(nid))
                    if node.get("type") == "t":
                        if rx is None or rx.search(text) or rx.search(str(nid)):
                            say(f"  T {child}  {text[:150]}")
                            shown[0] += 1
                            if shown[0] >= limit:
                                return
                    elif level < depth:
                        say(f"  {'  ' * level}l {nid}  {text[:80]}")
                        walk(child + "/", level + 1)
            walk(url, 0)
            return
        if mode == "pxq":
            body_json = base64.b64decode(extra[0]).decode()
            status, headers, body = fetch(url, data=body_json.encode(),
                                          headers={"Content-Type": "application/json"})
            summary(url, status, headers, body)
            say("  " + decode(body, headers)[:int(extra[1]) if len(extra) > 1 else 3000])
            return
        status, headers, body = fetch(url, timeout=180 if mode in ("xls", "xlsrow", "zip", "pdf") else TIMEOUT)
        summary(url, status, headers, body)
        if mode == "head" or status >= 400 and mode not in ("text",):
            if status >= 400:
                say("  " + strip(decode(body, headers))[:300])
            return
        if mode == "text":
            n = int(extra[0]) if extra else 1500
            say("  " + strip(decode(body, headers))[:n])
        elif mode == "grep":
            n = int(extra[1]) if len(extra) > 1 else 40
            text = decode(body, headers)
            hits = re.findall(extra[0], text)
            say(f"  {len(hits)} matches")
            for h in hits[:n]:
                say("  " + (h if isinstance(h, str) else " / ".join(h))[:300])
        elif mode == "links":
            n = int(extra[1]) if len(extra) > 1 else 80
            text = decode(body, headers)
            rx = re.compile(extra[0], re.I) if extra else None
            seen = 0
            for href, label in re.findall(r"""(?is)<a\b[^>]*?href\s*=\s*["']([^"']+)["'][^>]*>(.*?)</a>""", text):
                label = strip(label)
                if rx and not (rx.search(href) or rx.search(label)):
                    continue
                say(f"  {urllib.parse.urljoin(url, html.unescape(href))}  [{label[:90]}]")
                seen += 1
                if seen >= n:
                    break
            say(f"  ({seen} links shown)")
        elif mode in ("xls", "xlsrow"):
            sheets = rows_of(body)
            if mode == "xls":
                nrows = int(extra[0]) if extra else 8
                nsheets = int(extra[1]) if len(extra) > 1 else 6
                say(f"  {len(sheets)} sheets: {list(sheets)[:60]}")
                for name in list(sheets)[:nsheets]:
                    rows = sheets[name]
                    say(f"  -- sheet {name!r}: {len(rows)} rows x {max((len(r) for r in rows), default=0)} cols")
                    shown = 0
                    for row in rows:
                        if any(c.strip() for c in row):
                            say("    " + show_row(row))
                            shown += 1
                            if shown >= nrows:
                                break
            else:
                name, rx = extra[0], re.compile(extra[1], re.I)
                n = int(extra[2]) if len(extra) > 2 else 30
                if name in sheets:
                    rows = sheets[name]
                elif name.isdigit() and int(name) < len(sheets):
                    rows = sheets[list(sheets)[int(name)]]
                else:
                    rows = []
                    say(f"  no sheet {name!r}; sheets are {list(sheets)[:40]}")
                hit = 0
                for i, row in enumerate(rows):
                    if rx.search(" ".join(row)):
                        say(f"    r{i}: " + show_row(row, 22, 40))
                        hit += 1
                        if hit >= n:
                            break
        elif mode == "zip":
            zf = zipfile.ZipFile(io.BytesIO(body))
            for info in zf.infolist()[:120]:
                say(f"  {info.file_size:>12,} {info.filename}")
        elif mode == "px":
            data = json.loads(decode(body, headers).lstrip("﻿"))
            if isinstance(data, list):
                for node in data[:200]:
                    say(f"  {node.get('type')} {node.get('id')}  {node.get('text')}")
            else:
                say(f"  title: {data.get('title')}")
                for var in data.get("variables", []):
                    vals = var.get("values", [])
                    texts = var.get("valueTexts", [])
                    sample = ", ".join(f"{v}={t}" for v, t in list(zip(vals, texts))[:12])
                    say(f"  var {var.get('code')} ({var.get('text')}): {len(vals)} values: {sample}")
        elif mode == "pdf":
            import pdfplumber
            rx = re.compile(extra[0], re.I)
            n = int(extra[1]) if len(extra) > 1 else 40
            hit = 0
            with pdfplumber.open(io.BytesIO(body)) as pdf:
                say(f"  {len(pdf.pages)} pages")
                for p, page in enumerate(pdf.pages):
                    for line in (page.extract_text() or "").splitlines():
                        if rx.search(line):
                            say(f"    p{p + 1}: {line[:200]}")
                            hit += 1
                            if hit >= n:
                                return
    except Exception as exc:  # the probe's product is the log
        say(f"  !! {type(exc).__name__}: {str(exc)[:300]}")


def main() -> int:
    for arg in sys.argv[1:]:
        probe(arg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
