#!/usr/bin/env python3
"""Read-only probes for Central Africa.

The DRC, the Republic of the Congo, Cameroon, the Central African Republic,
Chad, Gabon, Equatorial Guinea, Sao Tome and Principe and Angola publish their
census tables as report PDFs and a few workbooks, from hosts that do not all
answer an automated client. This prints what is there before a reader is
written. Nothing is written and nothing is committed; the output is the log.

Each argument is one probe, ``mode:url`` with optional ``~~`` parts after it.
Every mode of ``surveys_probe`` works here (head, text, grep, links, js, post,
zip, xls, csv, cdx, pdf), and these are added:

    cdxf:URLPREFIX~~REGEX[~~N]     Internet Archive captures under a prefix whose
                                   address matches REGEX (newest per address)
    cdxm:URLPREFIX~~MIMETYPE[~~N]  Internet Archive captures under a prefix of one
                                   media type (application/pdf), newest per address
    wbav:URL                       the Internet Archive's closest capture of URL
    rows:URL[~~REGEX[~~N]]         an HTML page's table rows, cells joined by " | ",
                                   the first N whose text matches REGEX
    pdfp:URL~~PAGES[~~WIDTH]       pdfplumber's text of the pages given (3-7,12)
    pdfl:URL~~PAGES[~~WIDTH]       the same pages rebuilt row by row from the words'
                                   coordinates, so a label stays with its figures
    pdfg:URL~~REGEX[~~N]           pdfplumber lines matching REGEX, with page numbers
    pdft:URL~~REGEX[~~N]           the pages whose text matches REGEX: their first
                                   lines (titles), to find which page holds a table
    xlsx:URL~~SHEETREGEX[~~ROWS[~~COLS]]
                                   every sheet's name and size, and the first ROWS
                                   rows of the sheets whose name matches
    gjz:URL~~MEMBERREGEX[~~TOLERANCE]
                                   a GeoJSON file, or the GeoJSON members of a zip whose
                                   names match: each feature's name and code
                                   properties and its outline simplified to TOLERANCE
                                   degrees (default 0.005), as WKT, to overlay offline

The workflow splits the command on whitespace and xargs reads quotes and
backslashes, so no part may hold a space, a quote or a backslash: a regex
says ``[ ]`` or ``.`` instead.

Usage:
    python -m scripts.fetch_census.central_africa_probe pdft:https://example.org/r.pdf~~Tableau
"""

from __future__ import annotations

import io
import json
import re
import sys
import urllib.parse

from . import surveys_probe as base


def say(line: str) -> None:
    print(line, flush=True)


def pages_of(spec: str, count: int) -> list[int]:
    out: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            lo, hi = part.split("-", 1)
            out.extend(range(int(lo), min(int(hi), count) + 1))
        else:
            out.append(int(part))
    return [p for p in out if 1 <= p <= count]


def get(url: str, timeout: int = 300) -> tuple[int, str, dict, bytes]:
    status, final, headers, body = base.fetch(url, timeout=timeout)
    base.summary(url, status, final, headers, body)
    return status, final, headers, body


def rows_of(page, tolerance: float = 3.0) -> list[str]:
    """A page's words regrouped into rows by their tops, left to right."""
    words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
    rows: list[tuple[float, list[tuple[float, str]]]] = []
    for word in sorted(words, key=lambda w: (round(w["top"], 1), w["x0"])):
        top = round(word["top"], 1)
        if rows and abs(rows[-1][0] - top) <= tolerance:
            rows[-1][1].append((word["x0"], word["text"]))
        else:
            rows.append((top, [(word["x0"], word["text"])]))
    return [" ".join(t for _, t in sorted(cells)) for _, cells in rows]


LABEL_KEY = re.compile(r"(?i)^(adm\d?_?(name|pcode|en|pt|fr|es)|admin\d(name|pcode)\w*|shape(name|id)|name\w*|pcode)$")


def outlines(body: bytes, member_rx: str, tolerance: float) -> None:
    """Every feature's labels and simplified outline, from GeoJSON or a zip of it."""
    import zipfile                                    # noqa: PLC0415
    from shapely.geometry import shape                # noqa: PLC0415
    files: list[tuple[str, bytes]] = []
    if body[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(body)) as z:
            names = z.namelist()
            say(f"  zip: {len(names)} members: {', '.join(names[:12])}")
            rx = re.compile(member_rx, re.I)
            files = [(n, z.read(n)) for n in names
                     if n.lower().endswith((".geojson", ".json")) and rx.search(n)]
    else:
        files = [("(body)", body)]
    for name, blob in files:
        data = json.loads(blob.decode("utf-8"))
        feats = data.get("features") or []
        say(f"  --- {name}: {len(feats)} features")
        for f in feats:
            props = f.get("properties") or {}
            label = " | ".join(f"{k}={v}" for k, v in props.items() if LABEL_KEY.match(str(k)))
            try:
                geom = shape(f["geometry"]).simplify(tolerance, preserve_topology=True)
                wkt = re.sub(r"(\d+\.\d{4})\d+", r"\1", geom.wkt)
            except Exception as exc:                  # noqa: BLE001
                wkt = f"(unreadable: {exc})"
            say(f"  F {label}")
            say(f"  G {wkt}")


def probe(arg: str) -> None:
    mode, _, rest = arg.partition(":")
    if mode in base.MODES:
        base.probe(arg)
        return
    parts = rest.split("~~")
    url, extra = parts[0], parts[1:]
    say(f"== {mode} {url} {' '.join(extra)}")
    if mode == "cdxf":
        rx = extra[0] if extra else ".*"
        n = int(extra[1]) if len(extra) > 1 else 80
        q = ("https://web.archive.org/cdx/search/cdx?url=" + urllib.parse.quote(url, safe="")
             + "&matchType=prefix&filter=statuscode:200&collapse=urlkey"
             + "&filter=" + urllib.parse.quote("original:.*" + rx + ".*", safe="")
             + "&limit=" + str(max(n * 3, 200)))
        status, _, headers, body = base.fetch(q, timeout=180)
        lines = base.decode(body, headers).splitlines()
        say(f"  HTTP {status}: {len(lines)} captures")
        for line in lines[:n]:
            f = line.split(" ")
            if len(f) >= 7:
                say(f"  {f[1]} {f[3]} {f[6]} {f[2]}")
        return
    if mode == "cdxm":
        mime = extra[0] if extra else "application/pdf"
        n = int(extra[1]) if len(extra) > 1 else 80
        q = ("https://web.archive.org/cdx/search/cdx?url=" + urllib.parse.quote(url, safe="")
             + "&matchType=prefix&filter=statuscode:200&collapse=urlkey"
             + "&filter=mimetype:" + urllib.parse.quote(mime, safe="")
             + "&limit=" + str(max(n * 3, 200)))
        status, _, headers, body = base.fetch(q, timeout=180)
        lines = base.decode(body, headers).splitlines()
        say(f"  HTTP {status}: {len(lines)} captures")
        for line in lines[:n]:
            f = line.split(" ")
            if len(f) >= 7:
                say(f"  {f[1]} {f[3]} {f[6]} {f[2]}")
        return
    if mode == "wbav":
        q = "https://archive.org/wayback/available?url=" + urllib.parse.quote(url, safe="")
        status, _, headers, body = base.fetch(q, timeout=120)
        say(f"  HTTP {status}: {base.decode(body, headers)[:600]}")
        return
    if mode == "rows":
        status, final, headers, body = get(url)
        say(f"  HTTP {status} {len(body):,} bytes")
        rx = re.compile(extra[0] if extra and extra[0] else ".", re.I)
        n = int(extra[1]) if len(extra) > 1 else 200
        text = base.decode(body, headers)
        shown = 0
        for row in re.finditer(r"(?is)<tr\b.*?</tr>", text):
            cells = [base.strip(c) for c in re.findall(r"(?is)<t[dh]\b[^>]*>(.*?)</t[dh]>", row.group(0))]
            line = " | ".join(c for c in cells)
            if cells and rx.search(line):
                say("  " + line[:400])
                shown += 1
                if shown >= n:
                    break
        say(f"  ({shown} rows shown)")
        return
    if mode not in ("pdfp", "pdfl", "pdfg", "pdft", "xlsx", "gjz"):
        say(f"?? unknown mode in {arg!r}")
        return
    status, final, headers, body = get(url)
    if status >= 400 or status < 0:
        say("  " + base.strip(base.decode(body, headers))[:400])
        return
    if mode == "gjz":
        outlines(body, extra[0] if extra and extra[0] else ".",
                 float(extra[1]) if len(extra) > 1 else 0.005)
        return
    if mode == "xlsx":
        if body[:2] != b"PK":
            say("  not a workbook: " + base.strip(base.decode(body[:3000], headers))[:400])
            return
        import openpyxl                              # noqa: PLC0415
        rx = re.compile(extra[0] if extra and extra[0] else ".", re.I)
        rows = int(extra[1]) if len(extra) > 1 else 8
        cols = int(extra[2]) if len(extra) > 2 else 20
        book = openpyxl.load_workbook(io.BytesIO(body), read_only=True, data_only=True)
        for ws in book.worksheets:
            say(f"  sheet {ws.title!r} {ws.max_row}x{ws.max_column}")
            if not rx.search(ws.title):
                continue
            for i, row in enumerate(ws.iter_rows(values_only=True)):
                if i >= rows:
                    break
                say("    " + base.show_row(["" if v is None else v for v in row], 18, cols))
        return
    if body[:4] != b"%PDF":
        say("  not a PDF: " + base.strip(base.decode(body[:3000], headers))[:400])
        return
    import pdfplumber                               # noqa: PLC0415
    with pdfplumber.open(io.BytesIO(body)) as pdf:
        count = len(pdf.pages)
        say(f"  {count} pages")
        if mode in ("pdfp", "pdfl"):
            width = int(extra[1]) if len(extra) > 1 else 240
            for number in pages_of(extra[0] if extra else "1", count):
                page = pdf.pages[number - 1]
                lines = rows_of(page) if mode == "pdfl" else (page.extract_text() or "").splitlines()
                say(f"  --- page {number} ---")
                for line in lines:
                    say("  " + line[:width])
            return
        rx = re.compile(extra[0] if extra else ".", re.I)
        n = int(extra[1]) if len(extra) > 1 else 60
        shown = 0
        for number, page in enumerate(pdf.pages, 1):
            text = page.extract_text() or ""
            if mode == "pdft":
                if rx.search(text):
                    head = [line for line in text.splitlines() if line.strip()][:3]
                    say(f"  p{number}: " + " / ".join(h[:120] for h in head))
                    shown += 1
            else:
                for line in text.splitlines():
                    if rx.search(line):
                        say(f"  p{number}: {line[:220]}")
                        shown += 1
                        if shown >= n:
                            break
            if shown >= n:
                break
        if not shown:
            say("  (no match)")


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        say(__doc__ or "")
        return 0
    for arg in argv:
        try:
            probe(arg)
        except Exception as exc:  # noqa: BLE001 - one failed probe must not stop the rest
            say(f"  !! {type(exc).__name__}: {str(exc)[:300]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
