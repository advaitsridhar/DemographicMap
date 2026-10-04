#!/usr/bin/env python3
"""Read-only probes for the census taken in the north of Cyprus.

The Turkish Cypriot administration in the north (not recognised
internationally) took a population and housing census on 4 December 2011
("2011 Nüfus ve Konut Sayımı"). Its results were published by the State
Planning Organisation (Devlet Planlama Örgütü, ``devplan.org``) and are now
kept by the statistics institute (``istatistik.gov.ct.tr``). Neither host's
layout is guessable from here, and the sandbox that writes the adapter cannot
reach either, so this asks the runner and prints only what a decision needs:
which files the hosts and the Internet Archive hold, and what is in them.

Each probe is named, and several run in one call:

    python -m scripts.fetch_census.cyprus_north_probe --run cdx_devplan,home

A probe that takes a URL reads it from ``--url`` (repeatable), from the live
host or, with ``--wayback TS``, from the Internet Archive's raw capture.

Nothing is written; the output is the log.
"""

from __future__ import annotations

import argparse
import html
import io
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

UA = "DemographicMap/1.0 (+https://github.com/advaitsridhar/DemographicMap) python-urllib"
TIMEOUT = 150
CDX = "https://web.archive.org/cdx/search/cdx"
TERMS = r"(?i).*(n%C3%BCfus|nufus|n%FCfus|say%C4%B1m|sayim|census|population).*"


def log(*args: Any) -> None:
    print(*args, flush=True)


def fetch(url: str, timeout: int = TIMEOUT) -> tuple[int, str, bytes]:
    """(status, content type, body); an HTTP error is returned, not raised."""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.headers.get("Content-Type", ""), resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers.get("Content-Type", "") if exc.headers else "", b""


def raw_url(url: str, wayback: str | None) -> str:
    return f"https://web.archive.org/web/{wayback}id_/{url}" if wayback else url


def cdx(query: dict[str, str], limit: int = 400) -> list[list[str]]:
    params = {"output": "json", "fl": "timestamp,original,mimetype,statuscode,length",
              "collapse": "urlkey", "limit": str(limit), **query}
    status, _, body = fetch(CDX + "?" + urllib.parse.urlencode(params), timeout=240)
    if status != 200:
        log(f"  CDX {query} -> HTTP {status}")
        return []
    rows = json.loads(body.decode("utf-8", "replace") or "[]")
    return rows[1:] if rows else []


def show_cdx(label: str, query: dict[str, str], limit: int = 400, keep: str | None = None) -> None:
    log(f"== CDX {label}: {query}")
    try:
        rows = cdx(query, limit)
    except Exception as exc:                              # noqa: BLE001 -- reported
        log(f"  {type(exc).__name__}: {str(exc)[:200]}")
        return
    if keep:
        rows = [r for r in rows if re.search(keep, urllib.parse.unquote(r[1]), re.I)]
    log(f"  {len(rows)} rows")
    for ts, orig, mime, status, length in rows:
        log(f"  {ts} {status} {mime[:28]:28} {length:>9} {urllib.parse.unquote(orig)}")


def links_of(body: str, base: str) -> list[tuple[str, str]]:
    out = []
    for m in re.finditer(r"""(?is)<a\b[^>]*?href\s*=\s*["']?([^"' >]+)["']?[^>]*>(.*?)</a>""", body):
        href = html.unescape(m.group(1))
        text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", m.group(2)))).strip()
        out.append((urllib.parse.urljoin(base, href), text))
    return out


def show_links(url: str, grep: str | None, wayback: str | None = None, limit: int = 120) -> None:
    target = raw_url(url, wayback)
    log(f"== links {target}")
    try:
        status, ctype, body = fetch(target)
    except Exception as exc:                              # noqa: BLE001 -- reported
        log(f"  {type(exc).__name__}: {str(exc)[:200]}")
        return
    log(f"  HTTP {status} {ctype} {len(body):,} bytes")
    if not body:
        return
    text = body.decode("utf-8", "replace")
    seen = set()
    shown = 0
    for href, label in links_of(text, url):
        if href in seen:
            continue
        seen.add(href)
        if grep and not re.search(grep, urllib.parse.unquote(href) + " " + label, re.I):
            continue
        log(f"  {label[:70]!r} -> {urllib.parse.unquote(href)}")
        shown += 1
        if shown >= limit:
            log("  ...")
            break
    if not shown:
        title = re.search(r"(?is)<title>(.*?)</title>", text)
        log(f"  no matching links; title {title.group(1).strip()[:120] if title else None!r}; "
            f"starts {' '.join(text[:300].split())!r}")


def show_head(url: str, wayback: str | None = None) -> None:
    target = raw_url(url, wayback)
    try:
        status, ctype, body = fetch(target)
    except Exception as exc:                              # noqa: BLE001 -- reported
        log(f"== {target}\n  {type(exc).__name__}: {str(exc)[:200]}")
        return
    log(f"== {target}\n  HTTP {status} {ctype} {len(body):,} bytes; starts {body[:8]!r}")


def show_pdf(url: str, wayback: str | None, pages: str | None, grep: str | None,
             chars: int = 4000) -> None:
    import pdfplumber
    target = raw_url(url, wayback)
    log(f"== pdf {target}")
    status, ctype, body = fetch(target, timeout=300)
    log(f"  HTTP {status} {ctype} {len(body):,} bytes")
    if status != 200 or not body.startswith(b"%PDF"):
        return
    with pdfplumber.open(io.BytesIO(body)) as pdf:
        n = len(pdf.pages)
        log(f"  {n} pages")
        wanted: list[int] = []
        for part in (pages or "").split(","):
            if "-" in part:
                a, b = part.split("-")
                wanted += list(range(int(a), int(b) + 1))
            elif part.strip():
                wanted.append(int(part))
        for i, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if wanted and i not in wanted:
                continue
            if not wanted and grep and not re.search(grep, text, re.I):
                continue
            if not wanted and not grep:
                first = " | ".join(line for line in text.splitlines()[:3])
                log(f"  p{i}: {first[:200]}")
                continue
            log(f"  --- page {i} ---")
            log(text[:chars])


def show_xls(url: str, wayback: str | None, rows: int = 40) -> None:
    target = raw_url(url, wayback)
    log(f"== workbook {target}")
    status, ctype, body = fetch(target, timeout=300)
    log(f"  HTTP {status} {ctype} {len(body):,} bytes; starts {body[:8]!r}")
    if status != 200:
        return
    if body[:2] == b"PK":
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(body), read_only=True, data_only=True)
        for ws in wb.worksheets:
            log(f"  sheet {ws.title!r} {ws.max_row}x{ws.max_column}")
            for r, row in enumerate(ws.iter_rows(values_only=True)):
                if r >= rows:
                    break
                log("   " + " | ".join("" if v is None else str(v)[:24] for v in row[:16]))
    elif body[:4] == b"\xd0\xcf\x11\xe0":
        import xlrd
        wb = xlrd.open_workbook(file_contents=body)
        for ws in wb.sheets():
            log(f"  sheet {ws.name!r} {ws.nrows}x{ws.ncols}")
            for r in range(min(rows, ws.nrows)):
                log("   " + " | ".join(str(v)[:24] for v in ws.row_values(r)[:16]))


# --- named probes -----------------------------------------------------------

def p_cdx_devplan(a: argparse.Namespace) -> None:
    show_cdx("devplan Nufus-2011 prefix", {"url": "devplan.org/Nufus-2011/", "matchType": "prefix"})
    show_cdx("devplan census terms", {"url": "devplan.org", "matchType": "domain",
                                      "filter": "original:" + TERMS}, limit=600)


def p_cdx_istatistik(a: argparse.Namespace) -> None:
    show_cdx("istatistik.gov.ct.tr census terms",
             {"url": "istatistik.gov.ct.tr", "matchType": "domain", "filter": "original:" + TERMS},
             limit=800)


def p_cdx_istatistik_files(a: argparse.Namespace) -> None:
    show_cdx("istatistik.gov.ct.tr files",
             {"url": "istatistik.gov.ct.tr", "matchType": "domain",
              "filter": "original:(?i).*\\.(pdf|xls|xlsx|zip)$"}, limit=1500)


def p_home(a: argparse.Namespace) -> None:
    grep = r"n[uü]fus|say[iı]m|census|population|yay[iı]n|istatistik"
    for url in ("http://www.devplan.org/", "https://www.devplan.org/",
                "https://istatistik.gov.ct.tr/", "http://www.devplan.org/Nufus-2011/"):
        show_links(url, grep)


def p_links(a: argparse.Namespace) -> None:
    for url in a.url:
        show_links(url, a.grep, a.wayback)


def p_head(a: argparse.Namespace) -> None:
    for url in a.url:
        show_head(url, a.wayback)


def p_pdf(a: argparse.Namespace) -> None:
    for url in a.url:
        show_pdf(url, a.wayback, a.pages, a.grep, a.chars)


def p_xls(a: argparse.Namespace) -> None:
    for url in a.url:
        show_xls(url, a.wayback, a.rows)


PROBES: dict[str, Callable[[argparse.Namespace], None]] = {
    "cdx_devplan": p_cdx_devplan, "cdx_istatistik": p_cdx_istatistik,
    "cdx_istatistik_files": p_cdx_istatistik_files, "home": p_home, "links": p_links,
    "head": p_head, "pdf": p_pdf, "xls": p_xls,
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True, help="comma-separated probe names: " + ", ".join(PROBES))
    ap.add_argument("--url", action="append", default=[])
    ap.add_argument("--wayback", help="read --url from this Internet Archive capture, raw")
    ap.add_argument("--grep", help="regex a link or page must match")
    ap.add_argument("--pages", help="PDF pages to print, e.g. 1-3,9")
    ap.add_argument("--chars", type=int, default=4000)
    ap.add_argument("--rows", type=int, default=40)
    args = ap.parse_args()
    for name in args.run.split(","):
        if name not in PROBES:
            raise SystemExit(f"cyprus_north_probe: no probe {name!r}; have {sorted(PROBES)}")
        try:
            PROBES[name](args)
        except Exception as exc:                          # noqa: BLE001 -- reported
            log(f"!! {name}: {type(exc).__name__}: {str(exc)[:300]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
