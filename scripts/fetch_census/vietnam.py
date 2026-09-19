#!/usr/bin/env python3
"""Viet Nam: ethnicity by province from the 2019 census, by whichever route
actually yields the table.

The 2019 Population and Housing Census counted every province's people by
ethnic group (Kinh and the 53 recognised minorities) and by religion. The
statistics office does not answer this project's runner, and the English
results volume that UNFPA co-published prints both breakdowns for the
country only (docs/SOURCES.md, "Viet Nam"). The owner's decision of
19 September 2026 is that the provincial table is to be read from whichever
of three routes yields it -- the office's own files, a Kaggle dataset that
carries them, or the Vietnamese Wikipedia's transcription -- with the route
named in every record's note, and a transcription called a transcription.

``--probe`` runs all three routes' reconnaissance in one runner dispatch
and prints what each answered: which office hosts respond and with what,
what Kaggle lists for the search terms, and which tables the Vietnamese
articles hold. Nothing is written by a probe; the log is its product.

Usage:
    python -m scripts.fetch_census.vietnam --probe
    python -m scripts.fetch_census.vietnam
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from ._shared import PROCESSED, http_json, log, record, write_json

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from probe_wikitable import tables  # noqa: E402

OUT = "vietnam_province.json"
USER_AGENT = ("Mozilla/5.0 (compatible; DemographicMap/1.0; "
              "+https://github.com/advaitsridhar/DemographicMap)")

# Route (a): the office's own files, and the co-publisher that mirrored the
# English volume. Each is asked for its headers only.
OFFICE_URLS = [
    "https://www.gso.gov.vn/",
    "https://www.nso.gov.vn/",
    "https://www.gso.gov.vn/en/data-and-statistics/2020/11/completed-results-of-the-2019-viet-nam-population-and-housing-census/",
    "https://www.gso.gov.vn/wp-content/uploads/2019/12/Ket-qua-toan-bo-Tong-dieu-tra-dan-so-va-nha-o-2019.pdf",
    "https://www.gso.gov.vn/wp-content/uploads/2020/07/01-Bao-cao-53-dan-toc-thieu-so-2019_ban-in.pdf",
    "http://tongdieutradanso.vn/",
    "https://vietnam.unfpa.org/en/publications/results-2019-population-and-housing-census",
    "https://vietnam.unfpa.org/en/publications",
    "https://data.vietnam.opendevelopmentmekong.net/api/3/action/package_search?q=ethnic+province&rows=10",
]

# Route (b): what to ask Kaggle's catalogue for.
KAGGLE_SEARCHES = ["vietnam census", "vietnam ethnic", "vietnam population province",
                   "vietnam religion", "dân tộc", "tổng điều tra dân số"]

# Route (c): the Vietnamese articles most likely to hold the table, and a
# handful of province articles whose "Dân cư" section may carry one.
WIKI_INSPECT = [
    ("vi", "Danh sách các dân tộc Việt Nam theo tỉnh thành"),
    ("vi", "Các dân tộc Việt Nam"),
    ("vi", "Danh sách các dân tộc Việt Nam"),
    ("vi", "Dân số Việt Nam"),
    ("vi", "Hà Giang"),
    ("vi", "Sơn La"),
    ("vi", "Đắk Lắk"),
    ("vi", "Trà Vinh"),
    ("vi", "Lạng Sơn"),
    ("vi", "Thành phố Hồ Chí Minh"),
    ("en", "Hà Giang province"),
    ("en", "Ethnic groups in Vietnam"),
]
WIKI_SEARCHES = [
    ("vi", '"dân tộc" tỉnh 2019 Tày Nùng Mông Kinh bảng'),
    ("vi", '"Tổng điều tra dân số" 2019 "dân tộc" tỉnh thành'),
    ("vi", 'dân tộc thiểu số theo tỉnh 2019'),
    ("en", 'Vietnam province ethnic groups 2019 census table'),
]


def head(url: str, timeout: int = 20) -> None:
    """Status, type and size of one URL, or the exact refusal."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT}, method="HEAD")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            log(f"  {resp.status} {resp.headers.get('Content-Type', '?')[:40]:40} "
                f"{resp.headers.get('Content-Length', '?'):>12}  {url}")
    except urllib.error.HTTPError as exc:
        if exc.code in (403, 405, 501):
            # Some hosts refuse HEAD and answer GET; ask for the first bytes.
            get(url, timeout=timeout, limit=0)
        else:
            log(f"  {exc.code} {url}")
    except Exception as exc:  # noqa: BLE001 -- the failure mode is the finding
        log(f"  !! {type(exc).__name__}: {str(exc)[:100]}  {url}")


def get(url: str, timeout: int = 30, limit: int = 300_000) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            blob = resp.read(limit) if limit else resp.read(1024)
            log(f"  {resp.status} {resp.headers.get('Content-Type', '?')[:40]:40} "
                f"{len(blob):>12}  {url}")
            return blob.decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        log(f"  {exc.code} {url}")
    except Exception as exc:  # noqa: BLE001
        log(f"  !! {type(exc).__name__}: {str(exc)[:100]}  {url}")
    return ""


def probe_office() -> None:
    log("== route (a): the office and its co-publisher")
    for url in OFFICE_URLS:
        if "unfpa.org" in url or "opendevelopmentmekong" in url:
            html = get(url)
            for href in sorted(set(re.findall(r'href="([^"]+)"', html))):
                if re.search(r"\.pdf|\.xlsx?|census|dieu-tra|dan-so|ethnic|dan-toc",
                             href, re.IGNORECASE):
                    log(f"      -> {href[:140]}")
            if "opendevelopmentmekong" in url and html:
                try:
                    for pkg in json.loads(html).get("result", {}).get("results", []):
                        log(f"      pkg {pkg.get('name')}: {pkg.get('title', '')[:80]}")
                        for res in pkg.get("resources", [])[:6]:
                            log(f"          {res.get('format', '?'):6} {res.get('url', '')[:120]}")
                except json.JSONDecodeError:
                    log("      (not JSON)")
        else:
            head(url)


def kaggle_auth() -> dict[str, str]:
    """The Authorization header Kaggle's REST API accepts, from the runner's
    environment; the value is used and never printed. The single-token form
    is a bearer token; the older username/key pair is basic auth."""
    token = os.environ.get("KAGGLE_API_TOKEN", "")
    if token:
        return {"Authorization": f"Bearer {token}"}
    user, key = os.environ.get("KAGGLE_USERNAME", ""), os.environ.get("KAGGLE_KEY", "")
    if user and key:
        cred = base64.b64encode(f"{user}:{key}".encode()).decode()
        return {"Authorization": f"Basic {cred}"}
    return {}


def kaggle_json(path: str, params: dict[str, str]) -> Any:
    url = f"https://www.kaggle.com/api/v1/{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **kaggle_auth()})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def probe_kaggle() -> None:
    log("== route (b): Kaggle's catalogue "
        f"({'with' if kaggle_auth() else 'without'} credentials)")
    seen: set[str] = set()
    for term in KAGGLE_SEARCHES:
        try:
            found = kaggle_json("datasets/list", {"search": term, "page": "1"})
        except Exception as exc:  # noqa: BLE001
            log(f"  search {term!r}: {type(exc).__name__}: {str(exc)[:120]}")
            continue
        log(f"  search {term!r}: {len(found)} datasets")
        for ds in found[:12]:
            ref = ds.get("ref") or f"{ds.get('ownerRef')}/{ds.get('datasetSlug')}"
            log(f"    {ref:50} {ds.get('totalBytes', 0):>12,}  {str(ds.get('title', ''))[:70]}")
            if ref in seen:
                continue
            seen.add(ref)
            title = str(ds.get("title", "")).lower()
            if not re.search(r"ethnic|census|dân tộc|điều tra|religion|province|tỉnh", title):
                continue
            try:
                files = kaggle_json(f"datasets/list/files/{ref}", {})
            except Exception as exc:  # noqa: BLE001
                log(f"      files: {type(exc).__name__}: {str(exc)[:100]}")
                continue
            for f in (files.get("datasetFiles") or [])[:15]:
                log(f"      {f.get('totalBytes', 0):>12,}  {f.get('name')}")


def wiki_api(lang: str, **params: str) -> Any:
    q = urllib.parse.urlencode({"format": "json", "formatversion": "2", **params})
    return http_json(f"https://{lang}.wikipedia.org/w/api.php?{q}", timeout=90,
                     cache=False)


def wikitext(lang: str, title: str) -> str:
    parsed = wiki_api(lang, action="parse", page=title, prop="wikitext",
                      redirects="1").get("parse") or {}
    return parsed.get("wikitext") or ""


def probe_wiki(rows_shown: int = 3) -> None:
    log("== route (c): Wikipedia")
    for lang, query in WIKI_SEARCHES:
        try:
            hits = wiki_api(lang, action="query", list="search", srsearch=query,
                            srlimit="12").get("query", {}).get("search", [])
            log(f"  [{lang}] search {query!r}: "
                + "; ".join(h["title"] for h in hits))
        except Exception as exc:  # noqa: BLE001
            log(f"  [{lang}] search {query!r}: {type(exc).__name__}: {str(exc)[:100]}")
    for lang, title in WIKI_INSPECT:
        try:
            text = wikitext(lang, title)
        except Exception as exc:  # noqa: BLE001
            log(f"  [{lang}] {title!r}: {type(exc).__name__}: {str(exc)[:100]}")
            continue
        found = tables(text)
        log(f"  [{lang}] {title!r}: {len(text):,} bytes, {len(found)} table(s)")
        for n, t in enumerate(found):
            if not t:
                continue
            log(f"     -- table {n}: {len(t)} rows x {len(t[0])} cols; "
                f"header {[c.strip()[:22] for c in t[0][:8]]}")
            for row in t[1:1 + rows_shown]:
                log(f"        {[c.strip()[:22] for c in row[:8]]}")
        # The sentences that name the census and an ethnic group, for an
        # article whose figures are prose and not a table.
        for m in re.finditer(r"[^\n]{0,200}(?:dân tộc|ethnic)[^\n]{0,300}", text):
            s = m.group(0)
            if re.search(r"2019|2009", s) and re.search(r"\d[\d.,]*\s?%|người", s):
                flat = " ".join(s.split())
                log(f"     ~ {flat[:400]}")
                break


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--probe", action="store_true",
                    help="reconnoitre the three routes and write nothing")
    ap.add_argument("--rows", type=int, default=3, help="sample rows per table, with --probe")
    args = ap.parse_args()
    if args.probe:
        probe_office()
        probe_kaggle()
        probe_wiki(args.rows)
        return 0
    raise SystemExit("vietnam: the reader is not built yet; run --probe first")


if __name__ == "__main__":
    raise SystemExit(main())
