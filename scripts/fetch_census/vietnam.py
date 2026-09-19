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
    "https://www.nso.gov.vn/",
    "https://www.nso.gov.vn/du-lieu-va-so-lieu-thong-ke/2020/11/ket-qua-toan-bo-tong-dieu-tra-dan-so-va-nha-o-nam-2019/",
    "https://www.nso.gov.vn/en/data-and-statistics/2020/11/completed-results-of-the-2019-viet-nam-population-and-housing-census/",
    "https://www.nso.gov.vn/?s=k%E1%BA%BFt+qu%E1%BA%A3+to%C3%A0n+b%E1%BB%99+t%E1%BB%95ng+%C4%91i%E1%BB%81u+tra+d%C3%A2n+s%E1%BB%91+2019",
    "https://www.nso.gov.vn/?s=53+d%C3%A2n+t%E1%BB%99c+thi%E1%BB%83u+s%E1%BB%91+2019",
    "https://www.nso.gov.vn/wp-content/uploads/2019/12/Ket-qua-toan-bo-Tong-dieu-tra-dan-so-va-nha-o-2019.pdf",
    "https://www.nso.gov.vn/wp-content/uploads/2020/07/01-Bao-cao-53-dan-toc-thieu-so-2019_ban-in.pdf",
    "http://tongdieutradanso.vn/",
    "https://data.vietnam.opendevelopmentmekong.net/api/3/action/package_show?id=population-and-distribution-of-ethnic-minorities-in-vietnam",
    "https://data.vietnam.opendevelopmentmekong.net/api/3/action/package_show?id=thong-tin-dan-s-dan-t-c-thi-u-s-2015",
    "https://data.vietnam.opendevelopmentmekong.net/api/3/action/package_search?q=d%C3%A2n+t%E1%BB%99c+2019&rows=10",
]
# A page of a PDF that crosses province with ethnic group names a minority
# and several provinces together; the contents pages name the tables.
PDF_ROW_TERMS = ["Tày", "Nùng"]
PDF_PROVINCE_TERMS = ["Hà Giang", "Lạng Sơn", "Cao Bằng", "Sơn La"]

# Route (b): what to ask Kaggle's catalogue for.
KAGGLE_SEARCHES = ["vietnam census", "vietnam ethnic", "vietnam population province",
                   "vietnam religion", "dân tộc", "tổng điều tra dân số"]

# Route (c): the Vietnamese articles most likely to hold the table, and a
# handful of province articles whose "Dân cư" section may carry one.
WIKI_INSPECT = [
    ("vi", "Các dân tộc Việt Nam"),
    ("vi", "Người Tày"),
    ("vi", "Người Mường"),
    ("vi", "Người Việt"),
    ("vi", "Người Khmer (Việt Nam)"),
    ("vi", "Bắc Kạn (tỉnh)"),
    ("vi", "Lào Cai"),
    ("vi", "Cao Bằng"),
    ("vi", "Thái Nguyên"),
    ("vi", "Điện Biên"),
    ("vi", "Hòa Bình"),
]
WIKI_SEARCHES = [
    ("vi", 'insource:"Tày" insource:"Nùng" insource:"Hà Giang" insource:"Lạng Sơn" insource:2019 insource:"Dao"'),
    ("vi", '"dân tộc" "tỉnh" 2019 "Kinh" "Tày" "Nùng" "Mông" "Dao" "Hà Giang" "Cao Bằng" "Lạng Sơn"'),
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


def pdf_pages(blob: bytes) -> list[str]:
    import io
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(blob))
    log(f"      {len(reader.pages)} pages")
    return [(page.extract_text() or "") for page in reader.pages]


MAIN_PDF = ("https://www.nso.gov.vn/wp-content/uploads/2019/12/"
            "Ket-qua-toan-bo-Tong-dieu-tra-dan-so-va-nha-o-2019.pdf")
ETHNONYMS = ["Tày", "Thái", "Mường", "Khmer", "Hoa", "Nùng", "Mông", "Dao",
             "Gia Rai", "Ê Đê", "Ba Na", "Sán Chay", "Chăm", "Cơ Ho", "Xơ Đăng"]
FAITHS = ["Phật giáo", "Công giáo", "Tin lành", "Cao Đài", "Hòa Hảo"]
PROVINCES = ["Hà Nội", "Hà Giang", "Cao Bằng", "Lạng Sơn", "Sơn La", "Điện Biên",
             "Đắk Lắk", "Trà Vinh", "Hồ Chí Minh", "An Giang", "Cà Mau", "Lào Cai"]


def page_rows(blob: bytes, number: int) -> str:
    """One page with its rows rebuilt from word coordinates, the way
    probe_pdf --layout does for a whole file."""
    import io
    import pdfplumber
    out = []
    with pdfplumber.open(io.BytesIO(blob)) as pdf:
        page = pdf.pages[number - 1]
        words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
        rows: list[tuple[float, list[tuple[float, str]]]] = []
        for w in sorted(words, key=lambda w: (round(w["top"], 1), w["x0"])):
            top = round(w["top"], 1)
            if rows and abs(rows[-1][0] - top) <= 2.0:
                rows[-1][1].append((w["x0"], w["text"]))
            else:
                rows.append((top, [(w["x0"], w["text"])]))
        for _top, cells in rows:
            out.append("  ".join(t for _x, t in sorted(cells)))
    return "\n".join(out)


def search_pdf(url: str, limit: int = 80_000_000, full: int = 2) -> None:
    """Which pages of the volume cross ethnic group (or religion) with a
    province, and what the contents pages promise."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                               "Accept": "application/pdf,*/*"})
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            blob = resp.read(limit)
    except Exception as exc:  # noqa: BLE001
        log(f"      !! {type(exc).__name__}: {str(exc)[:100]}")
        return
    log(f"      {len(blob):,} bytes")
    if not blob.startswith(b"%PDF"):
        log(f"      not a PDF: starts {blob[:60]!r}")
        return
    try:
        pages = pdf_pages(blob)
    except Exception as exc:  # noqa: BLE001
        log(f"      !! cannot read: {type(exc).__name__}: {str(exc)[:100]}")
        return
    for n in (5, 6, 7, 8):
        if n <= len(pages):
            body = "\n".join(line.rstrip() for line in pages[n - 1].splitlines() if line.strip())
            log(f"      -- contents page {n}:\n{body[:3500]}")
    for label, terms, need in (("ethnic", ETHNONYMS, 6), ("religion", FAITHS, 4)):
        hits: list[tuple[int, list[str]]] = []
        for n, page in enumerate(pages, 1):
            if sum(t in page for t in terms) >= need:
                hits.append((n, [pv for pv in PROVINCES if pv in page]))
        log(f"      {len(hits)} page(s) name {need}+ {label} terms; "
            f"{sum(1 for _n, pv in hits if pv)} of them beside a province")
        compact = [f"p{n}{'[' + ','.join(pv) + ']' if pv else ''}" for n, pv in hits]
        log("      " + " ".join(compact)[:3000])
        shown = 0
        for n, pv in hits:
            if not pv or shown >= full:
                continue
            shown += 1
            body = "\n".join(line.rstrip() for line in pages[n - 1].splitlines() if line.strip())
            log(f"      -- page {n} ({label}), pypdf text:\n{body[:2500]}")
            try:
                log(f"      -- page {n} ({label}), rows by coordinate:\n{page_rows(blob, n)[:3500]}")
            except Exception as exc:  # noqa: BLE001
                log(f"      (rows failed: {type(exc).__name__}: {str(exc)[:80]})")


def probe_office() -> None:
    log("== route (a): the office and its co-publisher")
    pdfs: list[str] = []
    for url in OFFICE_URLS:
        if url.lower().endswith(".pdf"):
            head(url)
            pdfs.append(url)
            continue
        html = get(url)
        if "opendevelopmentmekong" in url and html:
            try:
                data = json.loads(html).get("result", {})
            except json.JSONDecodeError:
                log("      (not JSON)")
                continue
            for pkg in (data.get("results") if isinstance(data, dict) and "results" in data
                        else [data]):
                log(f"      pkg {pkg.get('name')}: {pkg.get('title', '')[:80]}")
                notes = " ".join(str(pkg.get("notes", "")).split())
                log(f"          notes: {notes[:600]}")
                for res in pkg.get("resources", [])[:8]:
                    log(f"          {res.get('format', '?'):6} {res.get('name', '')[:60]!r} "
                        f"{res.get('url', '')}")
                    if str(res.get("format", "")).upper() == "CSV":
                        body = get(res.get("url", ""), limit=2500)
                        for line in body.splitlines()[:8]:
                            log(f"              {line[:200]}")
            continue
        for href in sorted(set(re.findall(r'href="([^"]+)"', html))):
            if re.search(r"\.pdf|\.xlsx?|\.zip|dieu-tra|dan-so|dan-toc|census|ethnic",
                         href, re.IGNORECASE) and "nso.gov.vn" in href:
                log(f"      -> {href[:160]}")
                if href.lower().endswith(".pdf") and re.search(
                        r"toan-bo|dan-toc|53|ket-qua|results", href, re.IGNORECASE):
                    pdfs.append(href)
    seen: set[str] = set()
    for url in pdfs:
        if url in seen:
            continue
        seen.add(url)
        log(f"  PDF {url}")
        search_pdf(url)


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
        for t in found:
            for row in t:
                if any(c.strip() in ("Mường", "Tày") for c in row[:3]):
                    log(f"     full row: {[c.strip()[:700] for c in row]}")
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
    ap.add_argument("--routes", default="abc",
                    help="which routes to probe: a (office pages), b (Kaggle), "
                         "c (Wikipedia), p (scan the results volume for the tables)")
    args = ap.parse_args()
    if args.probe:
        if "a" in args.routes:
            probe_office()
        if "b" in args.routes:
            probe_kaggle()
        if "c" in args.routes:
            probe_wiki(args.rows)
        if "p" in args.routes:
            log(f"== route (a): the results volume {MAIN_PDF}")
            search_pdf(MAIN_PDF, full=args.rows)
        return 0
    raise SystemExit("vietnam: the reader is not built yet; run --probe first")


if __name__ == "__main__":
    raise SystemExit(main())
