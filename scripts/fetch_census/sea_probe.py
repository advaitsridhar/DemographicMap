#!/usr/bin/env python3
"""Southeast Asia reconnaissance: what each route serves, before a reader.

Read-only; nothing is written and the output is the log -- except ``strips``,
which writes page images for a table with no readable text layer, to be
removed once read. Each subcommand answers one question and prints only what
decides it.

* ``hdx ISO[,ISO...]`` -- every HDX dataset for the country that carries a
  population table (COD-PS, the Census Bureau's subnational series, others):
  its licence, its resources, and for each CSV or workbook sheet of a COD-PS
  the header, the row count and whether it splits by sex and five-year age.
* ``spa URL`` -- a single-page application's own API paths: the page, its
  scripts, and every ``api/...`` path those scripts name.
* ``get URL [URL...]`` -- status, type, length and the opening of each body,
  for endpoints found by ``spa``.
* ``xl URL --sheet NAME`` -- named sheets of a workbook, a window of rows.
* ``zip URL`` -- a zip's members and the opening lines of the first few.
* ``strips CDX-PATTERN`` -- Thailand's 2000 census provincial final reports,
  whose text layer is font-encoded: page 1 (the key indicators) of every
  captured report, cut to its title and three rows of the 2000 column --
  total population, Thai nationality, Buddhism -- with their English labels,
  stacked into a few JPEGs under ``data/processed/page_images`` to be read.

Usage:
    python -m scripts.fetch_census.sea_probe hdx THA,LAO
    python -m scripts.fetch_census.sea_probe spa https://example.org/app/
    python -m scripts.fetch_census.sea_probe get https://example.org/api/x
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from ._shared import log

HDX = "https://data.humdata.org/api/3/action"
UA = "DemographicMap/1.0 (+https://github.com/advaitsridhar/DemographicMap)"
TIMEOUT = 90
AGE = re.compile(r"^[TFM]_?\d{1,2}_\d{1,2}$|^[TFM]_?\d{1,2}_?plus$", re.I)


def fetch(url: str, *, timeout: int = TIMEOUT, accept: str | None = None,
          limit: int | None = None) -> tuple[int, str, bytes]:
    headers = {"User-Agent": UA}
    if accept:
        headers["Accept"] = accept
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as fh:
            body = fh.read(limit) if limit else fh.read()
            return fh.status, fh.headers.get("Content-Type", ""), body
    except urllib.error.HTTPError as err:
        return err.code, err.headers.get("Content-Type", "") if err.headers else "", \
            err.read()[:2000] if hasattr(err, "read") else b""


def hdx(path: str, **params: Any) -> Any:
    url = f"{HDX}/{path}?" + urllib.parse.urlencode(params)
    status, _, body = fetch(url, accept="application/json")
    if status != 200:
        raise SystemExit(f"HDX {path} answered {status}")
    return json.loads(body)["result"]


def describe_table(name: str, header: list[str], rows: int) -> None:
    ages = [c for c in header if AGE.match(c.strip())]
    sexes = sorted({c.strip()[0].upper() for c in ages})
    head = ", ".join(header[:14]) + (f" ... (+{len(header) - 14})" if len(header) > 14 else "")
    log(f"        {name}: {rows} rows; {len(header)} cols; age cols {len(ages)} "
        f"sexes {''.join(sexes) or '-'}")
    log(f"          [{head}]")
    if ages:
        log(f"          ages: {ages[0]} .. {ages[-1]}")


def read_resource(resource: dict[str, Any]) -> None:
    name = str(resource.get("name") or "")
    low = name.lower()
    url = str(resource.get("url") or "")
    if not low.endswith((".csv", ".xlsx")):
        return
    status, ctype, body = fetch(url, timeout=180)
    if status != 200:
        log(f"        {name}: HTTP {status}")
        return
    if low.endswith(".csv"):
        text = body.decode("utf-8-sig", "replace")
        reader = csv.reader(io.StringIO(text))
        header = next(reader, [])
        n = sum(1 for _ in reader)
        describe_table(name, header, n)
        return
    import openpyxl
    try:
        book = openpyxl.load_workbook(io.BytesIO(body), read_only=True, data_only=True)
    except Exception as err:  # noqa: BLE001 -- reported
        log(f"        {name}: unreadable workbook {type(err).__name__}")
        return
    for sheet in book.worksheets:
        rows = sheet.iter_rows(values_only=True)
        header = [str(c).strip() if c is not None else "" for c in next(rows, [])]
        n = sum(1 for _ in rows)
        describe_table(f"{name} [{sheet.title}]", [h for h in header if h], n)


def cmd_hdx(codes: list[str], tables: bool) -> None:
    for code in codes:
        found = hdx("package_search", fq=f"groups:{code.lower()}", q="population",
                    rows=60)
        packages = found.get("results") or []
        log(f"== {code}: {found.get('count')} datasets match 'population'")
        for p in packages:
            org = (p.get("organization") or {}).get("name", "")
            name = str(p.get("name"))
            keep = name.startswith("cod-ps") or "census" in name or "subnational" in name \
                or "census" in org or "age" in name
            if not keep:
                continue
            log(f"  {name} [{org}] licence={p.get('license_id')} "
                f"{p.get('license_other') or ''} ref={p.get('dataset_date')}")
            meth = p.get("methodology_other") or p.get("methodology") or ""
            if meth:
                log(f"      method: {str(meth)[:200]}")
            for r in p.get("resources") or ():
                log(f"      - {str(r.get('name'))[:90]} ({r.get('format')}, "
                    f"{r.get('size') or '?'} B)")
                if tables and name.startswith("cod-ps"):
                    read_resource(r)


def cmd_res(datasets: list[str], peek: bool, rows: int = 5) -> None:
    """An HDX dataset's resources with their URLs; with --peek, each workbook's
    sheets and first ``rows`` rows, read on the runner."""
    for name in datasets:
        p = hdx("package_show", id=name)
        log(f"== {name}: licence={p.get('license_id')} "
            f"{p.get('license_other') or ''} method={p.get('methodology_other') or p.get('methodology')}")
        for r in p.get("resources") or ():
            log(f"  - {r.get('name')} ({r.get('format')}, {r.get('size') or '?'} B)")
            log(f"    {r.get('url')}")
            if not peek or not str(r.get("name") or "").lower().endswith((".xlsx", ".csv")):
                continue
            status, _, body = fetch(str(r.get("url")), timeout=600)
            if status != 200:
                log(f"    HTTP {status}")
                continue
            if str(r.get("name")).lower().endswith(".csv"):
                lines = body.decode("utf-8-sig", "replace").splitlines()
                for line in lines[:6]:
                    log(f"    | {line[:300]}")
                log(f"    {len(lines)} lines")
                continue
            import openpyxl
            book = openpyxl.load_workbook(io.BytesIO(body), read_only=True, data_only=True)
            for sheet in book.worksheets:
                log(f"    sheet {sheet.title!r}: {sheet.max_row} rows x {sheet.max_column} cols")
                for i, row in enumerate(sheet.iter_rows(values_only=True)):
                    if i >= rows:
                        break
                    cells = ["" if c is None else str(c) for c in row]
                    log(f"    | {' | '.join(cells[:24])[:400]}")


def cmd_xl(url: str, sheets: list[str], rows: int, cols: int, width: int,
           start: int, find: str = "") -> None:
    """Named sheets of a workbook (xlsx or xls), rows ``start`` to ``start + rows``;
    with ``find``, instead every cell of those sheets matching that pattern."""
    status, _, body = fetch(url, timeout=600)
    log(f"{url}: HTTP {status} {len(body):,} B")
    if status != 200:
        return
    if url.lower().split("?")[0].endswith(".xls"):
        import xlrd
        book = xlrd.open_workbook(file_contents=body)
        names = book.sheet_names()
        get = lambda n: [[book.sheet_by_name(n).cell_value(r, c)  # noqa: E731
                          for c in range(book.sheet_by_name(n).ncols)]
                         for r in range(book.sheet_by_name(n).nrows)]
    else:
        import openpyxl
        book = openpyxl.load_workbook(io.BytesIO(body), read_only=True, data_only=True)
        names = book.sheetnames
        get = lambda n: [list(r) for r in book[n].iter_rows(values_only=True)]  # noqa: E731
    log(f"  sheets: {names}")
    for name in names:
        if sheets and not any(re.fullmatch(s, name) for s in sheets):
            continue
        table = get(name)
        log(f"  -- {name!r}: {len(table)} rows")
        if find:
            for i, row in enumerate(table):
                for j, c in enumerate(row):
                    if c is not None and re.search(find, str(c)):
                        log(f"   r{i} c{j}: {str(c).strip()[:width]}")
            continue
        for i, row in enumerate(table[start:start + rows], start=start):
            cells = ["" if c is None else str(c).strip()[:width] for c in row[:cols]]
            log(f"   {i:>4} | " + " | ".join(cells))


def cmd_zip(url: str, members: int, lines: int, encoding: str) -> None:
    """A zip's members, and the first lines of the first few of them."""
    import zipfile
    try:
        status, _, body = fetch(url, timeout=900)
    except Exception as err:  # noqa: BLE001 -- reported
        log(f"{url}: {type(err).__name__}: {err}")
        return
    log(f"{url}: HTTP {status} {len(body):,} B")
    if status != 200:
        log("  " + " ".join(body[:300].decode("utf-8", "replace").split()))
        return
    zf = zipfile.ZipFile(io.BytesIO(body))
    infos = zf.infolist()
    log(f"  {len(infos)} members")
    for info in infos[:400]:
        log(f"    {info.filename}  {info.file_size:,} B")
    for info in infos[:members]:
        if info.is_dir():
            continue
        raw = zf.read(info)
        log(f"  == {info.filename}")
        if info.filename.lower().endswith((".xls", ".xlsx")):
            log("    (workbook; read with xl)")
            continue
        text = raw.decode(encoding, "replace")
        for line in text.splitlines()[:lines]:
            log(f"    | {line[:300]}")


def cmd_spa(url: str) -> None:
    try:
        status, ctype, body = fetch(url)
    except Exception as err:  # noqa: BLE001 -- a DNS failure is an answer too
        log(f"{url}: {type(err).__name__}: {err}")
        return
    text = body.decode("utf-8", "replace")
    log(f"{url}: HTTP {status} {ctype} {len(body)} B")
    scripts = re.findall(r"<script[^>]+src=[\"']([^\"']+)", text)
    paths: set[str] = set(re.findall(r"""["'`]([^"'`\s]*api/[^"'`\s]{2,160})["'`]""", text))
    for src in scripts[:25]:
        full = urllib.parse.urljoin(url, src)
        try:
            s, _, js = fetch(full, timeout=120)
        except Exception as err:  # noqa: BLE001 -- reported
            log(f"  script {full}: {type(err).__name__}: {err}")
            continue
        jtext = js.decode("utf-8", "replace")
        found = set(re.findall(r"""["'`]([^"'`\s]*api/[^"'`\s]{2,160})["'`]""", jtext))
        found |= set(re.findall(r"""["'`](https?://[^"'`\s]{6,160})["'`]""", jtext))
        log(f"  script {full}: HTTP {s} {len(js)} B, {len(found)} paths")
        paths |= found
    for p in sorted(paths)[:300]:
        log(f"    {p}")


def html_rows(body: bytes) -> list[list[list[str]]]:
    """Every <table> of a page as rows of cell texts, nested tables kept apart."""
    from html.parser import HTMLParser

    class Rows(HTMLParser):
        def __init__(self) -> None:
            super().__init__(convert_charrefs=True)
            self.stack: list[list[list[str]]] = []
            self.done: list[list[list[str]]] = []
            self.cell: list[str] | None = None

        def handle_starttag(self, tag: str, attrs: Any) -> None:
            if tag == "table":
                self.stack.append([])
            elif tag == "tr" and self.stack:
                self.stack[-1].append([])
            elif tag in ("td", "th") and self.stack:
                if not self.stack[-1]:
                    self.stack[-1].append([])
                self.cell = []

        def handle_endtag(self, tag: str) -> None:
            if tag in ("td", "th") and self.cell is not None and self.stack:
                self.stack[-1][-1].append(" ".join("".join(self.cell).split()))
                self.cell = None
            elif tag == "table" and self.stack:
                self.done.append(self.stack.pop())

        def handle_data(self, data: str) -> None:
            if self.cell is not None:
                self.cell.append(data)

    for encoding in ("utf-8", "tis-620", "cp874", "latin-1"):
        try:
            text = body.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    parser = Rows()
    parser.feed(text)
    return parser.done


def cmd_table(urls: list[str], grep: str, head: int, cols: int, width: int) -> None:
    """Each page's tables: the first ``head`` rows of every table with at least
    four columns, and every row whose cells match ``grep``."""
    for url in urls:
        try:
            status, _, body = fetch(url, timeout=180)
        except Exception as err:  # noqa: BLE001 -- reported
            log(f"{url}: {type(err).__name__}: {err}")
            continue
        log(f"{url}: HTTP {status} {len(body):,} B")
        if status != 200:
            continue
        for t, rows in enumerate(html_rows(body)):
            wide = max((len(r) for r in rows), default=0)
            if wide < 4:
                continue
            log(f"  table {t}: {len(rows)} rows, up to {wide} cells")
            for i, row in enumerate(rows):
                if i < head or (grep and any(re.search(grep, c) for c in row)):
                    log(f"    r{i}: " + " | ".join(c[:width] for c in row[:cols]))


def cmd_get(urls: list[str], chars: int) -> None:
    for url in urls:
        try:
            status, ctype, body = fetch(url, timeout=120)
        except Exception as err:  # noqa: BLE001 -- reported
            log(f"{url}: {type(err).__name__}: {err}")
            continue
        text = body[: chars * 4].decode("utf-8", "replace")
        log(f"{url}: HTTP {status} {ctype} {len(body)} B")
        log("  " + " ".join(text.split())[:chars])


def cmd_dgs(terms: list[str], pages: int) -> None:
    """data.gov.sg datasets whose name names every term, walking the v2 list."""
    import os
    import time
    base = "https://api-production.data.gov.sg/v2/public/api/datasets"
    key = next((os.environ[k] for k in ("DEMOGRAPHICMAP", "DATA_GOV_SG_KEY")
                if os.environ.get(k)), None)
    hits = 0
    for page in range(1, pages + 1):
        body = None
        for attempt in range(4):
            time.sleep(0.8 * (attempt + 1))
            req = urllib.request.Request(f"{base}?page={page}", headers={"User-Agent": UA})
            if key:
                req.add_header("x-api-key", key)
            try:
                with urllib.request.urlopen(req, timeout=60) as fh:
                    body = json.loads(fh.read())
                break
            except Exception:  # noqa: BLE001 -- throttled or cut; retried
                body = None
        if body is None:
            log(f"  page {page}: no JSON after 4 attempts; stopping")
            break
        datasets = (body.get("data") or {}).get("datasets") or []
        if not datasets:
            log(f"  page {page}: empty; stopping")
            break
        for entry in datasets:
            name = str(entry.get("name") or "")
            if all(t in name.lower() for t in terms):
                hits += 1
                log(f"  {entry.get('datasetId')}  {name}  "
                    f"[{entry.get('managedByAgencyName') or ''}] "
                    f"{str(entry.get('lastUpdatedAt') or '')[:10]}")
    log(f"  {hits} datasets name all of {terms}")


def cmd_cdx(pattern: str, limit: int, match: str) -> None:
    """The Wayback Machine's captures under a URL pattern: one line per URL."""
    url = ("http://web.archive.org/cdx/search/cdx?" + urllib.parse.urlencode(
        {"url": pattern, "output": "json", "limit": str(limit),
         "filter": "statuscode:200", "collapse": "urlkey"}))
    try:
        status, _, body = fetch(url, timeout=180)
    except Exception as err:  # noqa: BLE001 -- reported
        log(f"cdx {pattern}: {type(err).__name__}: {err}")
        return
    if status != 200:
        log(f"cdx {pattern}: HTTP {status}")
        return
    rows = json.loads(body or b"[]")
    keep = [r for r in rows[1:] if not match or re.search(match, r[2])]
    log(f"cdx {pattern}: {len(rows) - 1} captures, {len(keep)} matching {match!r}")
    for r in keep:
        log(f"  {r[1]} {r[4]} {r[3][:30]} {r[2]}")


def cmd_wpmedia(base: str, searches: list[str], pages: int) -> None:
    """A WordPress site's uploads matching each search: the real file paths.

    Brunei's DEPS taught this: the links its pages print redirect to a 404,
    and the media API lists where every upload actually is.
    """
    for search in searches:
        total = 0
        for page in range(1, pages + 1):
            url = (f"{base.rstrip('/')}/wp-json/wp/v2/media?per_page=100&page={page}"
                   f"&search={urllib.parse.quote(search)}")
            status, _, body = fetch(url, accept="application/json")
            if status != 200:
                log(f"  {search!r} page {page}: HTTP {status} "
                    f"{' '.join(body[:160].decode('utf-8', 'replace').split())}")
                break
            items = json.loads(body)
            if not items:
                break
            for item in items:
                total += 1
                log(f"  {str(item.get('date'))[:10]} {item.get('source_url')}")
            if len(items) < 100:
                break
        log(f"== {search!r}: {total} uploads")


STRIP_DIR = "data/processed/page_images"
# The key-indicator rows cut out, counted down the 2000 column below its
# header as the Ranong report prints them: 1 the total population ('000),
# 13 Thai nationality (%), 14 Buddhism (%).
STRIP_ROWS = (1, 13, 14)


def bands(profile: Any, gap: int) -> list[tuple[int, int]]:
    """Runs of non-zero entries, joined across gaps of up to ``gap``."""
    out: list[tuple[int, int]] = []
    for i, v in enumerate(profile):
        if not v:
            continue
        if out and i - out[-1][1] <= gap:
            out[-1] = (out[-1][0], i)
        else:
            out.append((i, i))
    return out


def key_rows(gray: Any, dpi: int) -> dict[str, Any]:
    """Where a key-indicators page puts its title and its 2000 column's rows.

    The table is ruled: full-width rules above the header, below it and at
    the foot, and three vertical lines -- before the 1990 column, between
    1990 and 2000, after 2000. The 2000 column is the pair of neighbouring
    lines nearest 53% across (Ranong: 49% and 56%); its rows are the runs of
    ink between the header's rule and the foot's.
    """
    import numpy as np
    dark = np.asarray(gray) < 128
    h, w = dark.shape
    gap = max(2, round(3 * dpi / 90))
    vlines = bands(dark.sum(axis=0) > 0.35 * h, 1)
    rules = bands(dark.sum(axis=1) > 0.5 * w, 1)
    found: dict[str, Any] = {"vlines": vlines, "rules": rules, "rows": [], "title": None}
    for y0, y1 in bands(dark.sum(axis=1) > 0, gap):
        xs = np.where(dark[y0:y1 + 1].any(axis=0))[0]
        if len(xs) and xs[-1] - xs[0] > 0.1 * w:
            found["title"] = (y0, y1)
            break
    pairs = [(a, b) for a, b in zip(vlines, vlines[1:]) if 0.04 * w < b[0] - a[1] < 0.11 * w]
    if not pairs or len(rules) < 3:
        return found
    left, right = min(pairs, key=lambda p: abs((p[0][1] + p[1][0]) / 2 - 0.528 * w))
    top, bottom = rules[1][1] + 3, rules[-1][0] - 3
    column = dark[top:bottom, left[1] + 3:right[0] - 2]
    rows = [(top + a, top + b) for a, b in bands(column.sum(axis=1) > 0, gap)]
    if rows:
        tall = sorted(b - a for a, b in rows)[len(rows) // 2]
        rows = [r for r in rows if r[1] - r[0] >= 0.5 * tall]
    found.update(column=(left[0], right[1]), rows=rows)
    return found


def patient_fetch(url: str, pause: float) -> tuple[int, str, bytes]:
    """``fetch`` after a pause, tried three times: the Wayback Machine refuses
    connections from a client that asks for one file after another without one
    (27 reports in, the first run, 9789a13)."""
    import time
    for wait in (pause, 30.0, 90.0):
        time.sleep(wait)
        try:
            return fetch(url, timeout=300)
        except (urllib.error.URLError, TimeoutError, ConnectionError) as err:
            log(f"    {type(err).__name__}: {err}; again after a wait")
    return fetch(url, timeout=300)


def cmd_strips(pattern: str, dpi: int, per: int, match: str, pages: int, name: str,
               pause: float) -> None:
    """Every captured report's key-indicator rows, cut out and stacked to be read."""
    import os

    import pdfplumber
    from PIL import Image, ImageDraw
    url = ("http://web.archive.org/cdx/search/cdx?" + urllib.parse.urlencode(
        {"url": pattern, "output": "json", "filter": ["statuscode:200", "mimetype:application/pdf"],
         "collapse": "urlkey"}, doseq=True))
    status, _, body = fetch(url, timeout=180)
    if status != 200:
        log(f"cdx {pattern}: HTTP {status}")
        return
    captures = sorted((r for r in json.loads(body or b"[]")[1:]
                       if not match or re.search(match, r[2])),
                      key=lambda r: r[2].rsplit("/", 1)[-1])
    log(f"cdx {pattern}: {len(captures)} reports matching {match!r}")
    os.makedirs(STRIP_DIR, exist_ok=True)
    pieces: list[Any] = []
    pad = round(8 * dpi / 90)
    for r in captures:
        stem = r[2].rsplit("/", 1)[-1].rsplit(".", 1)[0]
        source = f"http://web.archive.org/web/{r[1]}id_/{r[2]}"
        try:
            status, _, pdf_bytes = patient_fetch(source, pause)
        except Exception as err:  # noqa: BLE001 -- reported
            log(f"  {stem}: {type(err).__name__}: {err}")
            continue
        if status != 200 or pdf_bytes[:5] != b"%PDF-":
            log(f"  {stem}: HTTP {status}, {len(pdf_bytes):,} B, not a PDF")
            continue
        cut: list[Any] = []
        note = ""
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for n in range(1, min(pages, len(pdf.pages)) + 1):
                gray = pdf.pages[n - 1].to_image(resolution=dpi).original.convert("L")
                where = key_rows(gray, dpi)
                rows = where["rows"]
                if len(rows) >= max(STRIP_ROWS) and where["title"]:
                    w = gray.width
                    t0, t1 = where["title"]
                    cut.append(gray.crop((round(0.2 * w), max(0, t0 - pad), round(0.8 * w),
                                          t1 + pad)))
                    for k in STRIP_ROWS:
                        y0, y1 = rows[k - 1]
                        cut.append(gray.crop((where["column"][0] - 2, y0 - pad,
                                              round(0.98 * w), y1 + pad)))
                    note = (f"page {n} of {len(pdf.pages)}; 2000 column x {where['column']}; "
                            f"{len(rows)} rows; rows {list(STRIP_ROWS)} at y "
                            f"{[rows[k - 1][0] for k in STRIP_ROWS]}")
                    break
                log(f"  {stem}: page {n}: {len(where['vlines'])} vertical lines, "
                    f"{len(where['rules'])} rules, {len(rows)} rows -- not the table")
            else:
                if len(pdf.pages):
                    whole = pdf.pages[0].to_image(resolution=dpi).original.convert("L")
                    cut.append(whole.resize((500, round(whole.height * 500 / whole.width))))
                    note = f"no key-indicator table on pages 1-{pages}: page 1 whole"
        label = Image.new("L", (520, 14), 255)
        ImageDraw.Draw(label).text((2, 1), f"{len(pieces) + 1}. {stem} ({r[1][:8]})", fill=0)
        pieces.append([label, *cut])
        log(f"  {len(pieces)}. {stem}: {r[1]} {len(pdf_bytes):,} B; {note}")
    for k in range(0, len(pieces), per):
        group = pieces[k:k + per]
        width = max(im.width for piece in group for im in piece)
        height = sum(im.height + 3 for piece in group for im in piece) + 6 * len(group)
        sheet = Image.new("L", (width, height), 255)
        y = 0
        for piece in group:
            for im in piece:
                sheet.paste(im, (0, y))
                y += im.height + 3
            ImageDraw.Draw(sheet).line((0, y + 2, width, y + 2), fill=128, width=2)
            y += 6
        path = f"{STRIP_DIR}/{name}-{k // per + 1:02d}.jpg"
        sheet.save(path, "JPEG", quality=80, optimize=True)
        log(f"  {path}: reports {k + 1}-{k + len(group)}, {width}x{height}, "
            f"{os.path.getsize(path):,} B")


def cmd_unstrip(match: str) -> None:
    """Remove the page images whose names match, once read."""
    import os
    if not os.path.isdir(STRIP_DIR):
        log(f"{STRIP_DIR} is not there")
        return
    gone = sorted(n for n in os.listdir(STRIP_DIR) if re.search(match, n))
    for name in gone:
        os.remove(f"{STRIP_DIR}/{name}")
    log(f"removed from {STRIP_DIR}: {', '.join(gone) or 'nothing'}")
    if not os.listdir(STRIP_DIR):
        os.rmdir(STRIP_DIR)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("res")
    r.add_argument("datasets", nargs="+")
    r.add_argument("--peek", action="store_true")
    r.add_argument("--rows", type=int, default=5)
    xl = sub.add_parser("xl")
    xl.add_argument("url")
    xl.add_argument("--sheet", action="append", default=[],
                    help="a regular expression a sheet's whole name must match; repeatable")
    xl.add_argument("--rows", type=int, default=40)
    xl.add_argument("--from", dest="start", type=int, default=0)
    xl.add_argument("--cols", type=int, default=16)
    xl.add_argument("--width", type=int, default=24)
    xl.add_argument("--find", default="",
                    help="print only the cells matching this pattern, with their places")
    z = sub.add_parser("zip")
    z.add_argument("url")
    z.add_argument("--members", type=int, default=3)
    z.add_argument("--lines", type=int, default=8)
    z.add_argument("--encoding", default="utf-8")
    x = sub.add_parser("cdx")
    x.add_argument("pattern")
    x.add_argument("--limit", type=int, default=2000)
    x.add_argument("--match", default="")
    w = sub.add_parser("wpmedia")
    w.add_argument("base")
    w.add_argument("searches", help="comma-separated search words")
    w.add_argument("--pages", type=int, default=5)
    d = sub.add_parser("dgs")
    d.add_argument("terms", help="comma-separated words every name must contain")
    d.add_argument("--pages", type=int, default=480)
    a = sub.add_parser("hdx")
    a.add_argument("codes")
    a.add_argument("--no-tables", action="store_true")
    b = sub.add_parser("spa")
    b.add_argument("url")
    t = sub.add_parser("table")
    t.add_argument("urls", nargs="+")
    t.add_argument("--grep", default="")
    t.add_argument("--head", type=int, default=4)
    t.add_argument("--cols", type=int, default=24)
    t.add_argument("--width", type=int, default=18)
    c = sub.add_parser("get")
    c.add_argument("urls", nargs="+")
    c.add_argument("--chars", type=int, default=400)
    s = sub.add_parser("strips")
    s.add_argument("pattern", help="a Wayback CDX URL pattern for the reports")
    s.add_argument("--dpi", type=int, default=120)
    s.add_argument("--per", type=int, default=16, help="reports to an image")
    s.add_argument("--match", default="", help="only the reports whose URL matches")
    s.add_argument("--pages", type=int, default=3, help="pages searched for the table")
    s.add_argument("--name", default="tha2000", help="the images' name, before their number")
    s.add_argument("--pause", type=float, default=5.0, help="seconds between two reports")
    u = sub.add_parser("unstrip")
    u.add_argument("match", help="a pattern the image names to remove match")
    args = ap.parse_args()
    if args.cmd == "strips":
        cmd_strips(args.pattern, args.dpi, args.per, args.match, args.pages, args.name,
                   args.pause)
        return 0
    if args.cmd == "unstrip":
        cmd_unstrip(args.match)
        return 0
    if args.cmd == "hdx":
        cmd_hdx([x.strip().upper() for x in args.codes.split(",") if x.strip()],
                not args.no_tables)
    elif args.cmd == "spa":
        cmd_spa(args.url)
    elif args.cmd == "res":
        cmd_res(args.datasets, args.peek, args.rows)
    elif args.cmd == "xl":
        cmd_xl(args.url, args.sheet, args.rows, args.cols, args.width, args.start, args.find)
    elif args.cmd == "zip":
        cmd_zip(args.url, args.members, args.lines, args.encoding)
    elif args.cmd == "cdx":
        cmd_cdx(args.pattern, args.limit, args.match)
    elif args.cmd == "wpmedia":
        cmd_wpmedia(args.base, [s for s in args.searches.split(",") if s], args.pages)
    elif args.cmd == "table":
        cmd_table(args.urls, args.grep, args.head, args.cols, args.width)
    elif args.cmd == "dgs":
        cmd_dgs([t.strip().lower() for t in args.terms.split(",") if t.strip()], args.pages)
    else:
        cmd_get(args.urls, args.chars)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
