#!/usr/bin/env python3
"""Lao PDR: ethnicity, religion and language by province from the census.

Reconnaissance first; the reader follows once --probe says which route
answers.  Usage:

    python -m scripts.fetch_census.laos --probe --routes ao
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from ._shared import RAW, download, http_json, log  # noqa: F401

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from probe_wikitable import tables  # noqa: E402

USER_AGENT = ("DemographicMap/1.0 (+https://github.com/advaitsridhar/DemographicMap) "
              "python-urllib")

# ---------------------------------------------------------------------------
# --probe: where the 4th Population and Housing Census 2015 might be readable.
# ---------------------------------------------------------------------------

# (label, url, link filter) -- a page is fetched and its matching links printed.
PAGES = [
    ("LSB home", "https://lsb.gov.la/", r"\.pdf|\.xlsx?|census|populat|ethnic"),
    ("LSB home (www)", "https://www.lsb.gov.la/", r"\.pdf|\.xlsx?|census|populat"),
    ("LSB English", "https://lsb.gov.la/en/", r"\.pdf|\.xlsx?|census|populat"),
    ("LaoSIS", "https://laosis.lsb.gov.la/", r"\.pdf|\.xlsx?|census|populat|tblInfo"),
    ("UNFPA Laos publications",
     "https://lao.unfpa.org/en/publications",
     r"\.pdf|census|publication"),
    ("UNFPA Laos census page",
     "https://lao.unfpa.org/en/publications/results-population-and-housing-census-2015-english-version",
     r"\.pdf"),
    ("Open Development Laos, census search",
     "https://data.laos.opendevelopmentmekong.net/api/3/action/package_search"
     "?q=census&rows=25", ""),
    ("Open Development Laos, ethnicity search",
     "https://data.laos.opendevelopmentmekong.net/api/3/action/package_search"
     "?q=ethnic&rows=25", ""),
    ("decide.la", "https://www.decide.la/en/", r"\.pdf|\.xlsx?|census|ethnic"),
]

# Files to ask for by name: the census volumes as several hosts spell them.
FILES = [
    "https://lao.unfpa.org/sites/default/files/pub-pdf/PHC-ENG-FNAL-WEB_0.pdf",
    "https://lao.unfpa.org/sites/default/files/pub-pdf/PHC-ENG-FNAL-WEB.pdf",
    "https://www.lsb.gov.la/wp-content/uploads/2021/03/PHC-ENG-FNAL-WEB.pdf",
    "https://lsb.gov.la/wp-content/uploads/2021/03/PHC-ENG-FNAL-WEB.pdf",
    "https://www.lsb.gov.la/pdf/PHC-ENG-FNAL-WEB.pdf",
    "https://www.unicef.org/laos/media/2216/file/LSIS%20II%20Report%20English.pdf",
]

HDX_SEARCHES = ["Lao PDR census", "Laos population housing census 2015",
                "Lao ethnicity", "Lao PDR subnational population"]

WIKI_INSPECT = [("en", "Provinces of Laos"), ("en", "Demographics of Laos"),
                ("en", "Ethnic groups in Laos"), ("en", "Religion in Laos"),
                ("lo", "ປະເທດລາວ"), ("en", "Savannakhet province"),
                ("en", "Xiangkhouang province")]
WIKI_SEARCHES = [("en", 'Laos census 2015 province ethnicity Khmu Hmong'),
                 ("lo", 'ສຳຫຼວດພົນລະເມືອງ 2015 ຊົນເຜົ່າ')]


def get(url: str, timeout: int = 45, limit: int = 400_000) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                               "Accept": "text/html,*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            blob = resp.read(limit)
            log(f"  {resp.status} {resp.headers.get('Content-Type', '?')[:40]:40} "
                f"{len(blob):>10}  {url}")
            return blob.decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        log(f"  {exc.code} {exc.reason}  {url}")
    except Exception as exc:  # noqa: BLE001 -- the failure mode is the finding
        log(f"  !! {type(exc).__name__}: {str(exc)[:120]}  {url}")
    return ""


def head(url: str, timeout: int = 45) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT}, method="HEAD")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            log(f"  {resp.status} {resp.headers.get('Content-Type', '?')[:40]:40} "
                f"{resp.headers.get('Content-Length', '?'):>12}  {url}")
    except urllib.error.HTTPError as exc:
        if exc.code in (403, 405, 501):
            get(url, timeout=timeout, limit=2048)
        else:
            log(f"  {exc.code} {exc.reason}  {url}")
    except Exception as exc:  # noqa: BLE001
        log(f"  !! {type(exc).__name__}: {str(exc)[:120]}  {url}")


def probe_pages() -> None:
    log("== route (a): the office, its partners and the open-data portal")
    for label, url, pattern in PAGES:
        log(f"  -- {label}")
        body = get(url)
        if not body:
            continue
        if "action/package_search" in url:
            try:
                result = json.loads(body).get("result", {})
            except json.JSONDecodeError:
                log(f"      not JSON: {' '.join(body[:200].split())!r}")
                continue
            log(f"      {result.get('count', 0)} dataset(s)")
            for pkg in result.get("results", [])[:25]:
                log(f"      pkg {pkg.get('name')}: {str(pkg.get('title', ''))[:80]}")
                for res in pkg.get("resources", [])[:8]:
                    log(f"          {str(res.get('format', '?')):6} "
                        f"{str(res.get('url', ''))[:130]}")
            continue
        hrefs = sorted(set(re.findall(r'href="([^"]+)"', body)))
        hits = [h for h in hrefs if not pattern or re.search(pattern, h, re.IGNORECASE)]
        log(f"      {len(hrefs)} links, {len(hits)} matching")
        for href in hits[:60]:
            log(f"      -> {href[:170]}")


def probe_files() -> None:
    log("== route (f): the candidate volumes, by name")
    for url in FILES:
        head(url)


def probe_hdx() -> None:
    log("== route (h): HDX")
    for query in HDX_SEARCHES:
        url = ("https://data.humdata.org/api/3/action/package_search?"
               + urllib.parse.urlencode({"q": query, "rows": "20"}))
        body = get(url, limit=2_000_000)
        if not body:
            continue
        try:
            result = json.loads(body).get("result", {})
        except json.JSONDecodeError:
            log("      not JSON")
            continue
        log(f"  search {query!r}: {result.get('count', 0)} dataset(s)")
        for pkg in result.get("results", [])[:20]:
            org = (pkg.get("organization") or {}).get("name", "?")
            fmts = sorted({str(r.get("format", "?")) for r in pkg.get("resources", [])})
            log(f"    {org:28} {str(pkg.get('name', ''))[:60]:60} {fmts}")


def wiki_api(lang: str, **params: str) -> dict:
    q = urllib.parse.urlencode({"format": "json", "formatversion": "2", **params})
    return http_json(f"https://{lang}.wikipedia.org/w/api.php?{q}", timeout=90, cache=False)


def probe_wiki(rows_shown: int = 3) -> None:
    log("== route (w): Wikipedia")
    for lang, query in WIKI_SEARCHES:
        try:
            hits = wiki_api(lang, action="query", list="search", srsearch=query,
                            srlimit="12").get("query", {}).get("search", [])
            log(f"  [{lang}] search {query!r}: " + "; ".join(h["title"] for h in hits))
        except Exception as exc:  # noqa: BLE001
            log(f"  [{lang}] search {query!r}: {type(exc).__name__}: {str(exc)[:100]}")
    for lang, title in WIKI_INSPECT:
        try:
            parsed = wiki_api(lang, action="parse", page=title, prop="wikitext",
                              redirects="1").get("parse") or {}
            text = parsed.get("wikitext") or ""
        except Exception as exc:  # noqa: BLE001
            log(f"  [{lang}] {title!r}: {type(exc).__name__}: {str(exc)[:100]}")
            continue
        found = tables(text)
        log(f"  [{lang}] {title!r}: {len(text):,} bytes, {len(found)} table(s)")
        for n, t in enumerate(found):
            if not t:
                continue
            log(f"     -- table {n}: {len(t)} rows x {len(t[0])} cols; "
                f"header {[c.strip()[:24] for c in t[0][:9]]}")
            for row in t[1:1 + rows_shown]:
                log(f"        {[c.strip()[:24] for c in row[:9]]}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--routes", default="afhw",
                    help="a (pages), f (candidate files), h (HDX), w (Wikipedia)")
    ap.add_argument("--rows", type=int, default=3)
    args = ap.parse_args()
    if not args.probe:
        raise SystemExit("laos: no reader yet; run with --probe")
    if "a" in args.routes:
        probe_pages()
    if "f" in args.routes:
        probe_files()
    if "h" in args.routes:
        probe_hdx()
    if "w" in args.routes:
        probe_wiki(args.rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
