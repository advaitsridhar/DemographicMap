#!/usr/bin/env python3
"""What a data portal actually links to, and whether those files exist.

Statistical offices publish their tables from a landing page whose links are
the only reliable index -- file naming conventions drift between census rounds,
and a guessed URL that 404s is indistinguishable from a dataset that was never
published. This fetches a page, prints the links matching a pattern, and then
asks each candidate file for its headers so size and type are known before an
adapter is written against it.

Read-only, and the output is the log.

Usage:
    python scripts/probe_links.py https://example.org/census --match religion,tabulados
    python scripts/probe_links.py --head https://example.org/data.zip
"""

from __future__ import annotations

import argparse
import gzip
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

TIMEOUT = 25
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; DemographicMap/1.0; "
                  "+https://github.com/advaitsridhar/DemographicMap)",
    "Accept": "text/html,application/xhtml+xml,*/*",
    "Accept-Language": "es-MX,es;q=0.9,en;q=0.8",
}


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={**HEADERS, "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        raw = resp.read()
        if resp.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
        return raw.decode("utf-8", "replace")


def head(url: str) -> None:
    """Size and type without pulling the file. Some hosts refuse HEAD, so a
    ranged GET is the fallback -- a 206 answers the same question."""
    for method in ("HEAD", "GET"):
        req = urllib.request.Request(url, method=method, headers=dict(HEADERS))
        if method == "GET":
            req.add_header("Range", "bytes=0-0")
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                size = resp.headers.get("Content-Range") or resp.headers.get("Content-Length")
                print(f"    {resp.status} {resp.headers.get('Content-Type','?')} "
                      f"size={size}")
                return
        except urllib.error.HTTPError as err:
            if method == "GET":
                print(f"    HTTP {err.code}")
        except Exception as err:                  # noqa: BLE001
            if method == "GET":
                print(f"    {type(err).__name__}: {str(err)[:80]}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("url")
    ap.add_argument("--match", default="",
                    help="comma-separated substrings; a link matches on href or text")
    ap.add_argument("--head", action="store_true",
                    help="treat the url as a file and report its headers only")
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--check", type=int, default=0,
                    help="also fetch headers for the first N matching links")
    args = ap.parse_args()

    if args.head:
        # A comma-separated list, because a portal that renders its links in
        # JavaScript -- INEGI's census page is 5 KB of shell and no anchors --
        # leaves testing candidate URLs as the only way to find the files, and
        # doing that one CI run at a time is unaffordable.
        for url in [u.strip() for u in args.url.split(",") if u.strip()]:
            print(url)
            head(url)
        return 0

    # A list here for the same reason as --head: a landing page is a guess too,
    # and finding out one CI run at a time which of half a dozen candidates is
    # the real index costs more than fetching all of them.
    for url in [u.strip() for u in args.url.split(",") if u.strip()]:
        page(url, args)
    return 0


def page(url: str, args: argparse.Namespace) -> None:
    print(f"page: {url}")
    try:
        html = fetch(url)
    except Exception as err:                      # noqa: BLE001
        print(f"  unreachable: {type(err).__name__}: {str(err)[:120]}")
        return
    print(f"  {len(html):,} bytes")

    wanted = [w.strip().lower() for w in args.match.split(",") if w.strip()]
    seen, hits = set(), []
    for m in re.finditer(r'<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.S | re.I):
        href = urllib.parse.urljoin(url, m.group(1))
        text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", m.group(2))).strip()
        blob = f"{href} {text}".lower()
        if wanted and not any(w in blob for w in wanted):
            continue
        if href in seen:
            continue
        seen.add(href)
        hits.append((href, text))

    print(f"  {len(hits)} matching link(s)")
    for href, text in hits[:args.limit]:
        print(f"  - {text[:70]}")
        print(f"    {href}")
    for href, _ in hits[:args.check]:
        print(f"  checking {href}")
        head(href)


if __name__ == "__main__":
    sys.exit(main())
