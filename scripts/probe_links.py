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

# Generous, and settable, because a slow office and an absent one are
# different findings and a short timeout cannot tell them apart. Bangladesh's
# BBS completes a TLS handshake in under a second and then takes far longer
# than this to answer a GET; reporting that as unreachable would be the same
# mistake as reading a 429 as an empty database.
TIMEOUT = 25
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; DemographicMap/1.0; "
                  "+https://github.com/advaitsridhar/DemographicMap)",
    "Accept": "text/html,application/xhtml+xml,*/*",
    "Accept-Language": "es-MX,es;q=0.9,en;q=0.8",
}


def fetch(url: str, accept: str = "", timeout: int = TIMEOUT) -> str:
    extra = {"Accept": accept} if accept else {}
    req = urllib.request.Request(
        url, headers={**HEADERS, **extra, "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        if resp.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
        return raw.decode("utf-8", "replace")


def head(url: str, accept: str = "", timeout: int = TIMEOUT) -> None:
    """Size and type without pulling the file. Some hosts refuse HEAD, so a
    ranged GET is the fallback -- a 206 answers the same question."""
    for method in ("HEAD", "GET"):
        headers = dict(HEADERS)
        if accept:
            # An API that content-negotiates reports a different Content-Type
            # per Accept, and reporting the type is the whole point of --head.
            headers["Accept"] = accept
        req = urllib.request.Request(url, method=method, headers=headers)
        if method == "GET":
            req.add_header("Range", "bytes=0-0")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
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
    ap.add_argument("url", nargs="+",
                    help="one or more URLs. Separate arguments rather than a "
                         "comma-joined list, because an SDMX data key contains "
                         "commas -- splitting on them tore "
                         "'data/STATSNZ,CEN23_ECI_017,1.0/all' into three "
                         "unreachable fragments.")
    ap.add_argument("--match", default="",
                    help="comma-separated substrings; a link matches on href or text")
    ap.add_argument("--head", action="store_true",
                    help="treat the url as a file and report its headers only")
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--timeout", type=int, default=TIMEOUT,
                    help="seconds to wait for each response")
    ap.add_argument("--check", type=int, default=0,
                    help="also fetch headers for the first N matching links")
    ap.add_argument("--accept", default="",
                    help="Accept header, for an API that content-negotiates "
                         "its format (SDMX, JSON-stat)")
    ap.add_argument("--find", default="",
                    help="print the parts of the body matching this regex, "
                         "for a page whose content is fetched by script")
    ap.add_argument("--raw", type=int, default=0,
                    help="print the first N bytes of the body instead of "
                         "parsing links; for JSON endpoints and catalogue APIs")
    args = ap.parse_args()

    if args.head:
        # --head splits on commas; page mode does not. The difference is not
        # arbitrary: --head takes plain file URLs, which never contain a
        # comma, and probe-source.yml passes a whole candidate list through
        # one string input. An SDMX data key *does* contain commas, and that
        # is what page mode has to carry through intact.
        for url in [u.strip() for arg in args.url
                    for u in arg.split(",") if u.strip()]:
            print(url)
            head(url, args.accept, args.timeout)
        return 0

    # Several pages in one run for the same reason as --head: a landing page is
    # a guess too, and finding out one CI run at a time which of half a dozen
    # candidates is the real index costs more than fetching all of them.
    for url in args.url:
        page(url, args)
    return 0


def page(url: str, args: argparse.Namespace) -> None:
    print(f"page: {url}")
    try:
        html = fetch(url, args.accept, args.timeout)
    except Exception as err:                      # noqa: BLE001
        # The whole message, not a slice of it. A TLS failure names the host
        # the certificate *is* valid for, and that name is the finding -- cut
        # at 120 characters it read "certificate is not valid f".
        print(f"  unreachable: {type(err).__name__}: {str(err)[:400]}")
        return
    print(f"  {len(html):,} bytes")
    # A page that is a script shell has the same bytes at every path -- BPS's
    # 2010 census service answers root, a table URL and a topic URL with one
    # identical 52,849-byte document -- so its anchors are the template's own
    # navigation and the data is somewhere its scripts know about. --find
    # prints just the parts of the body that match, rather than the body.
    if args.find:
        hits = sorted(set(re.findall(args.find, html)))
        print(f"  {len(hits)} distinct match(es) for {args.find!r}")
        for hit in hits[:args.limit]:
            print(f"    {hit if isinstance(hit, str) else hit}")
        return
    # A catalogue API answers in JSON, which has no anchors to parse.
    if args.raw:
        print(html[:args.raw])
        return

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
        head(href, timeout=args.timeout)


if __name__ == "__main__":
    sys.exit(main())
