#!/usr/bin/env python3
"""Read-only probes for the statistical offices of the Arab states and Israel.

The Gulf offices publish through open-data portals of three kinds --
OpenDataSoft (Bahrain's data.gov.bh, Qatar's data.gov.qa), CKAN (Saudi
Arabia's open data) and single-page apps with a JSON API behind them -- and
the Levant's through WordPress sites and SharePoint libraries. Each of the
subcommands below answers one question about one of those and prints only
what decides it. Nothing is written and nothing is committed but the log.
Every argument is one whitespace-free token, as the workflow splits its
command on whitespace.

Subcommands:

    ods BASE [--search WORDS] [--rows N]
        An OpenDataSoft catalogue: each dataset's id, title, record count and
        field names. WORDS is a '+'-joined search.
    odsrows BASE DATASET [--where W] [--select S] [--group-by G] [--rows N]
        Records of one OpenDataSoft dataset (Explore API v2.1).
    get URL [URL ...] [--grep REGEX] [--links REGEX] [--chars N]
        Status, type and length of each answer; the text around each REGEX
        match, the links whose address or label match, or the opening.
    wayback URL [--rows N]
        The Internet Archive's captures of a URL pattern (CDX), newest last.

Usage:
    python -m scripts.fetch_census.west_asia_probe ods https://www.data.gov.bh --search population
    python -m scripts.fetch_census.west_asia_probe get https://example.org --links xlsx
"""

from __future__ import annotations

import argparse
import html
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from ._shared import log

UA = ("DemographicMap/1.0 (+https://github.com/advaitsridhar/DemographicMap) "
      "python-urllib")
TIMEOUT = 90
CDX = "https://web.archive.org/cdx/search/cdx"


def fetch(url: str, *, accept: str | None = None, limit: int | None = None
          ) -> tuple[int, str, bytes]:
    headers = {"User-Agent": UA}
    if accept:
        headers["Accept"] = accept
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as fh:
            body = fh.read(limit) if limit else fh.read()
            return fh.status, fh.headers.get("Content-Type", ""), body
    except urllib.error.HTTPError as err:
        body = b""
        try:
            body = err.read()[:3000]
        except Exception:  # noqa: BLE001
            pass
        return err.code, (err.headers.get("Content-Type", "") if err.headers else ""), body
    except Exception as err:  # noqa: BLE001 -- a probe reports, it does not raise
        return -1, type(err).__name__, str(err).encode()


def text_of(body: bytes, ctype: str) -> str:
    m = re.search(r"charset=([\w-]+)", ctype or "")
    enc = m.group(1) if m else "utf-8"
    try:
        return body.decode(enc, "replace")
    except LookupError:
        return body.decode("utf-8", "replace")


def plain(page: str) -> str:
    page = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", page)
    page = re.sub(r"(?i)<br\s*/?>|</(p|div|tr|li|h\d|td|th)>", "\n", page)
    page = re.sub(r"<[^>]+>", " ", page)
    page = html.unescape(page)
    return "\n".join(" ".join(line.split()) for line in page.split("\n") if line.strip())


def cmd_ods(base: str, search: str | None, rows: int) -> None:
    base = base.rstrip("/")
    params = {"limit": str(min(rows, 100))}
    if search:
        params["where"] = " OR ".join(f'search("{w}")' for w in search.split("+"))
    offset = 0
    shown = 0
    while shown < rows:
        params["offset"] = str(offset)
        url = f"{base}/api/explore/v2.1/catalog/datasets?" + urllib.parse.urlencode(params)
        status, ctype, body = fetch(url, accept="application/json")
        if status != 200:
            log(f"{url}: {status} {ctype} {body[:300]!r}")
            return
        data = json.loads(body)
        results = data.get("results") or []
        if offset == 0:
            log(f"{base}: {data.get('total_count')} datasets")
        for ds in results:
            meta = (ds.get("metas") or {}).get("default") or {}
            fields = [f.get("name") for f in ds.get("fields") or []]
            log(f"  {ds.get('dataset_id')} | {meta.get('title')} | records={meta.get('records_count')}"
                f" | modified={str(meta.get('modified'))[:10]}")
            log(f"      fields: {', '.join(str(f) for f in fields)[:400]}")
            shown += 1
        if not results or len(results) < int(params["limit"]):
            break
        offset += len(results)


def cmd_odsrows(base: str, dataset: str, where: str | None, select: str | None,
                group_by: str | None, rows: int) -> None:
    base = base.rstrip("/")
    params = {"limit": str(min(rows, 100))}
    if where:
        params["where"] = where
    if select:
        params["select"] = select
    if group_by:
        params["group_by"] = group_by
    url = (f"{base}/api/explore/v2.1/catalog/datasets/{dataset}/records?"
           + urllib.parse.urlencode(params))
    status, ctype, body = fetch(url, accept="application/json")
    if status != 200:
        log(f"{url}: {status} {ctype} {body[:500]!r}")
        return
    data = json.loads(body)
    log(f"{dataset}: total_count={data.get('total_count')}")
    for rec in data.get("results") or []:
        log("  " + json.dumps(rec, ensure_ascii=False)[:600])


def cmd_get(urls: list[str], grep: str | None, links: str | None, chars: int,
            context: int) -> None:
    for url in urls:
        status, ctype, body = fetch(url)
        log(f"== {url}\n   {status} {ctype} {len(body):,} bytes")
        page = text_of(body, ctype)
        if links:
            pat = re.compile(links, re.I)
            seen = set()
            for m in re.finditer(r'(?is)<a\b[^>]*?href\s*=\s*["\']([^"\']+)["\'][^>]*>(.*?)</a>',
                                 page):
                href, label = html.unescape(m.group(1)), plain(m.group(2))[:120]
                full = urllib.parse.urljoin(url, href)
                if (pat.search(href) or pat.search(label)) and full not in seen:
                    seen.add(full)
                    log(f"   - {label!r} -> {full}")
            log(f"   {len(seen)} matching links")
        if grep:
            text = plain(page) if "html" in ctype.lower() else page
            hits = 0
            for m in re.finditer(grep, text, flags=re.I):
                a, b = max(0, m.start() - context), min(len(text), m.end() + context)
                log("   ~ " + " ".join(text[a:b].split()))
                hits += 1
                if hits >= 40:
                    break
            log(f"   {hits} matches for {grep!r}")
        if not links and not grep:
            text = plain(page) if "html" in ctype.lower() else page
            log("   " + text[:chars].replace("\n", "\n   "))


def cmd_wayback(pattern: str, rows: int) -> None:
    url = CDX + "?" + urllib.parse.urlencode({
        "url": pattern, "output": "json", "limit": str(rows),
        "collapse": "urlkey", "filter": "statuscode:200"})
    status, ctype, body = fetch(url)
    if status != 200:
        log(f"{url}: {status} {body[:300]!r}")
        return
    rows_ = json.loads(body or b"[]")
    log(f"{pattern}: {max(0, len(rows_) - 1)} captures")
    for row in rows_[1:]:
        log("  " + " ".join(str(c) for c in row[1:5]))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["ods", "odsrows", "get", "wayback"])
    ap.add_argument("target", nargs="+")
    ap.add_argument("--search")
    ap.add_argument("--where")
    ap.add_argument("--select")
    ap.add_argument("--group-by")
    ap.add_argument("--rows", type=int, default=60)
    ap.add_argument("--grep")
    ap.add_argument("--links")
    ap.add_argument("--chars", type=int, default=1500)
    ap.add_argument("--context", type=int, default=150)
    args = ap.parse_args()
    if args.cmd == "ods":
        for base in args.target:
            cmd_ods(base, args.search, args.rows)
    elif args.cmd == "odsrows":
        cmd_odsrows(args.target[0], args.target[1], args.where, args.select,
                    args.group_by, args.rows)
    elif args.cmd == "get":
        cmd_get(args.target, args.grep, args.links, args.chars, args.context)
    elif args.cmd == "wayback":
        for pattern in args.target:
            cmd_wayback(pattern, args.rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
