#!/usr/bin/env python3
"""Read-only probes for Southern Africa and the Indian Ocean.

South Africa, Namibia, Botswana, Zimbabwe, Zambia, Malawi, Mozambique, Lesotho,
Eswatini, Madagascar, Mauritius, Comoros and Seychelles publish their census
tables as report PDFs, workbooks and a few JSON services, from hosts that do
not all answer an automated client. This prints what is there before a reader
is written. Nothing is written and nothing is committed; the output is the log.

Each argument is one probe, ``mode:url`` with optional ``~~`` parts after it.
Every mode of ``surveys_probe`` works here (head, text, grep, links, js, post,
zip, xls, csv, cdx, pdf), and these are added:

    cdxf:URLPREFIX~~REGEX[~~N]     Internet Archive captures under a prefix whose
                                   address matches REGEX (newest per address)
    json:URL[~~N]                  a JSON answer, indented, its first N characters
    keys:URL[~~N]                  a JSON list's first item's keys and N items' values
    pdfp:URL~~PAGES[~~WIDTH]       pdfplumber's text of the pages given (3-7,12)
    pdfg:URL~~REGEX[~~N]           pdfplumber lines matching REGEX, with page numbers
    pdft:URL~~REGEX[~~N]           the pages whose text matches REGEX: their first
                                   lines (titles), to find which page holds a table
    sheets:URL                     every sheet of a workbook (or of the first
                                   workbook in a zip): name, size, first text cells
    sheet:URL~~NAME[~~ROWS[~~COLS]] one sheet's rows (NAME may be its number, 1-based)
    attrs:URL~~ATTR[~~N[~~CHARS]]  every value of one HTML attribute on the page
                                   (a chart widget's data-chart_data), unescaped

The workflow splits the command on whitespace and xargs reads quotes and
backslashes, so no part may hold a space, a quote or a backslash: a regex
says ``[ ]`` or ``.`` instead.

Usage:
    python -m scripts.fetch_census.southern_africa_probe json:https://example.org/api
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


def workbook_rows(body: bytes) -> list[tuple[str, list[list]]]:
    """[(sheet name, rows)] of a workbook, or of the first workbook in a zip."""
    if body[:2] == b"PK":
        import zipfile                              # noqa: PLC0415
        with zipfile.ZipFile(io.BytesIO(body)) as zf:
            names = zf.namelist()
            if "[Content_Types].xml" not in names:
                inner = [n for n in names if n.lower().endswith((".xlsx", ".xls", ".xlsm"))]
                if not inner:
                    raise ValueError(f"zip holds no workbook: {names[:10]}")
                say(f"  zip member {inner[0]} ({len(names)} members)")
                body = zf.read(inner[0])
    out: list[tuple[str, list[list]]] = []
    if body[:2] == b"PK":
        import openpyxl                             # noqa: PLC0415
        wb = openpyxl.load_workbook(io.BytesIO(body), read_only=True, data_only=True)
        for ws in wb.worksheets:
            out.append((ws.title, [["" if v is None else v for v in row]
                                   for row in ws.iter_rows(values_only=True)]))
    else:
        import xlrd                                 # noqa: PLC0415
        wb = xlrd.open_workbook(file_contents=body)
        for sh in wb.sheets():
            out.append((sh.name, [sh.row_values(r) for r in range(sh.nrows)]))
    return out


def cell(value: object, width: int = 22) -> str:
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return " ".join(str(value).split())[:width]


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
        # The archive compiles the filter as one expression, and a global
        # flag such as (?i) is refused anywhere but at its start (HTTP 500).
        flags = ""
        while rx.startswith("(?") and ")" in rx and rx[2:rx.index(")")].isalpha():
            flags += rx[:rx.index(")") + 1]
            rx = rx[rx.index(")") + 1:]
        q = ("https://web.archive.org/cdx/search/cdx?url=" + urllib.parse.quote(url, safe="")
             + "&matchType=prefix&filter=statuscode:200&collapse=urlkey"
             + "&filter=" + urllib.parse.quote("original:" + flags + ".*" + rx + ".*", safe="")
             + "&limit=" + str(max(n * 3, 200)))
        status, _, headers, body = base.fetch(q, timeout=180)
        lines = base.decode(body, headers).splitlines()
        say(f"  HTTP {status}: {len(lines)} captures")
        for line in lines[:n]:
            f = line.split(" ")
            if len(f) >= 7:
                say(f"  {f[1]} {f[3]} {f[6]} {f[2]}")
        return
    if mode not in ("json", "keys", "pdfp", "pdfg", "pdft", "sheets", "sheet", "attrs"):
        say(f"?? unknown mode in {arg!r}")
        return
    status, final, headers, body = get(url)
    if status >= 400 or status < 0:
        say("  " + base.strip(base.decode(body, headers))[:400])
        return
    if mode == "attrs":
        import html as html_lib                     # noqa: PLC0415
        attr = extra[0] if extra else "data-chart_data"
        n = int(extra[1]) if len(extra) > 1 else 40
        chars = int(extra[2]) if len(extra) > 2 else 1500
        page = base.decode(body, headers)
        found = re.findall(re.escape(attr) + r"""\s*=\s*(?:'([^']*)'|"([^"]*)")""", page)
        say(f"  {len(found)} values of {attr}")
        for single, double in found[:n]:
            value = html_lib.unescape(single or double)
            say("  -- " + " ".join(value.split())[:chars])
        return
    if mode in ("sheets", "sheet"):
        sheets = workbook_rows(body)
        if mode == "sheets":
            for number, (name, rows) in enumerate(sheets, 1):
                texts = [cell(v, 70) for row in rows[:8] for v in row
                         if isinstance(v, str) and v.strip()][:3]
                width = max((len(r) for r in rows), default=0)
                say(f"  {number:>3} {name!r} {len(rows)}x{width}: " + " / ".join(texts))
            return
        want = extra[0] if extra else "1"
        rows_n = int(extra[1]) if len(extra) > 1 else 60
        cols_n = int(extra[2]) if len(extra) > 2 else 24
        chosen = [s for s in sheets if s[0] == want] or \
            ([sheets[int(want) - 1]] if want.isdigit() and int(want) <= len(sheets) else [])
        if not chosen:
            say(f"  no sheet {want!r}; sheets: {[s[0] for s in sheets][:60]}")
            return
        name, rows = chosen[0]
        say(f"  sheet {name!r}: {len(rows)} rows")
        for i, row in enumerate(rows[:rows_n]):
            cells = [cell(v) for v in row[:cols_n]]
            while cells and not cells[-1]:
                cells.pop()
            if cells:
                say(f"  {i + 1:>4}: " + " | ".join(cells))
        return
    if mode in ("json", "keys"):
        try:
            payload = json.loads(base.decode(body, headers))
        except ValueError:
            say("  not JSON: " + base.strip(base.decode(body[:3000], headers))[:600])
            return
        if mode == "json":
            n = int(extra[0]) if extra else 4000
            say(json.dumps(payload, indent=1, ensure_ascii=False)[:n])
            return
        n = int(extra[0]) if extra else 10
        items = payload if isinstance(payload, list) else next(
            (v for v in payload.values() if isinstance(v, list)), [payload]) \
            if isinstance(payload, dict) else [payload]
        say(f"  {len(items)} items")
        if items and isinstance(items[0], dict):
            say(f"  keys: {list(items[0])}")
        for item in items[:n]:
            say("  " + json.dumps(item, ensure_ascii=False)[:300])
        return
    if body[:4] != b"%PDF":
        say("  not a PDF: " + base.strip(base.decode(body[:3000], headers))[:400])
        return
    import pdfplumber                               # noqa: PLC0415
    with pdfplumber.open(io.BytesIO(body)) as pdf:
        count = len(pdf.pages)
        say(f"  {count} pages")
        if mode == "pdfp":
            width = int(extra[1]) if len(extra) > 1 else 220
            for number in pages_of(extra[0] if extra else "1", count):
                text = pdf.pages[number - 1].extract_text() or ""
                say(f"  --- page {number} ---")
                for line in text.splitlines():
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
