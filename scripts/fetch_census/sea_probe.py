#!/usr/bin/env python3
"""Southeast Asia reconnaissance: what each route serves, before a reader.

Read-only; nothing is written and the output is the log. Each subcommand
answers one question and prints only what decides it.

* ``hdx ISO[,ISO...]`` -- every HDX dataset for the country that carries a
  population table (COD-PS, the Census Bureau's subnational series, others):
  its licence, its resources, and for each CSV or workbook sheet of a COD-PS
  the header, the row count and whether it splits by sex and five-year age.
* ``spa URL`` -- a single-page application's own API paths: the page, its
  scripts, and every ``api/...`` path those scripts name.
* ``get URL [URL...]`` -- status, type, length and the opening of each body,
  for endpoints found by ``spa``.

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


def cmd_spa(url: str) -> None:
    status, ctype, body = fetch(url)
    text = body.decode("utf-8", "replace")
    log(f"{url}: HTTP {status} {ctype} {len(body)} B")
    scripts = re.findall(r"<script[^>]+src=[\"']([^\"']+)", text)
    paths: set[str] = set(re.findall(r"""["'`]([^"'`\s]*api/[^"'`\s]{2,160})["'`]""", text))
    for src in scripts[:25]:
        full = urllib.parse.urljoin(url, src)
        s, _, js = fetch(full, timeout=120)
        jtext = js.decode("utf-8", "replace")
        found = set(re.findall(r"""["'`]([^"'`\s]*api/[^"'`\s]{2,160})["'`]""", jtext))
        found |= set(re.findall(r"""["'`](https?://[^"'`\s]{6,160})["'`]""", jtext))
        log(f"  script {full}: HTTP {s} {len(js)} B, {len(found)} paths")
        paths |= found
    for p in sorted(paths)[:300]:
        log(f"    {p}")


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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
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
    c = sub.add_parser("get")
    c.add_argument("urls", nargs="+")
    c.add_argument("--chars", type=int, default=400)
    args = ap.parse_args()
    if args.cmd == "hdx":
        cmd_hdx([x.strip().upper() for x in args.codes.split(",") if x.strip()],
                not args.no_tables)
    elif args.cmd == "spa":
        cmd_spa(args.url)
    elif args.cmd == "wpmedia":
        cmd_wpmedia(args.base, [s for s in args.searches.split(",") if s], args.pages)
    elif args.cmd == "dgs":
        cmd_dgs([t.strip().lower() for t in args.terms.split(",") if t.strip()], args.pages)
    else:
        cmd_get(args.urls, args.chars)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
