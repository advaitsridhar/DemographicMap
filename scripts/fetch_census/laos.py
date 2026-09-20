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

from ._shared import RAW, download, http_get, http_json, log  # noqa: F401

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


# ---------------------------------------------------------------------------
# The census volume itself.
# ---------------------------------------------------------------------------

CENSUS_PDF = "https://lao.unfpa.org/sites/default/files/pub-pdf/PHC-ENG-FNAL-WEB_0.pdf"

PROVINCE_TERMS = ["Vientiane Capital", "Phongsaly", "Luangnamtha", "Luang Namtha",
                  "Oudomxay", "Bokeo", "Luangprabang", "Luang Prabang", "Huaphanh",
                  "Houaphan", "Xayabury", "Xayaboury", "Xiengkhuang", "Xiangkhouang",
                  "Borikhamxay", "Bolikhamxai", "Khammuane", "Khammouane",
                  "Savannakhet", "Saravane", "Salavan", "Sekong", "Xekong",
                  "Champasack", "Champasak", "Attapeu", "Xaysomboun", "Xaisomboun"]
ETHNONYMS = ["Khmou", "Khmu", "Hmong", "Phouthay", "Makong", "Katang", "Leu", "Lue",
             "Akha", "Katu", "Ta-oy", "Taoy", "Brao", "Oy", "Ngouan", "Ngae", "Suay",
             "Harak", "Yrou", "Triang", "Lavy", "Lamed", "Musur", "Iumien", "Sila",
             "Hor", "Lolo", "Pako", "Nhaheun", "Cheng", "Toum", "Phong", "Thene"]
FAITHS = ["Buddhis", "Christian", "Bahai", "Baha'i", "Islam", "Muslim",
          "Animis", "No religion", "Religion"]
LANGUAGE_TERMS = ["Mother tongue", "mother tongue", "Language spoken", "Lao-Tai",
                  "Mon-Khmer", "Chine-Tibet", "Sino-Tibetan", "Hmong-Mien",
                  "Hmong-Iewmien", "ethno-linguistic", "Ethno-linguistic"]


def page_texts(path: Path) -> list[str]:
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    log(f"  {len(reader.pages)} pages")
    return [(page.extract_text() or "") for page in reader.pages]


def probe_volume(samples: int = 2, contents: str = "") -> None:
    """Which pages of the census volume cross one of the three fields with a
    province, and what its contents pages promise."""
    log(f"== route (p): the census volume {CENSUS_PDF}")
    pages = page_texts(download(CENSUS_PDF, RAW / "laos" / "PHC-ENG-FNAL-WEB_0.pdf"))
    wanted = [int(n) for n in contents.split(",") if n.strip().isdigit()]
    for n in wanted:
        if 1 <= n <= len(pages):
            body = "\n".join(line.rstrip() for line in pages[n - 1].splitlines()
                             if line.strip())
            log(f"  -- page {n}:\n{body[:4000]}")
    for label, terms, need in (("ethnic", ETHNONYMS, 5), ("religion", FAITHS, 3),
                               ("language", LANGUAGE_TERMS, 2)):
        hits = [(n, [pv for pv in PROVINCE_TERMS if pv in page])
                for n, page in enumerate(pages, 1)
                if sum(t in page for t in terms) >= need]
        log(f"  {len(hits)} page(s) name {need}+ {label} terms; "
            f"{sum(1 for _n, pv in hits if pv)} of them beside a province")
        log("    " + " ".join(f"p{n}{'[' + ','.join(sorted(set(pv))[:3]) + ']' if pv else ''}"
                              for n, pv in hits)[:2500])
        shown = 0
        for n, pv in hits:
            if not pv or shown >= samples:
                continue
            shown += 1
            body = "\n".join(line.rstrip() for line in pages[n - 1].splitlines()
                             if line.strip())
            log(f"  -- page {n} ({label}):\n{body[:3000]}")
    # Every line that looks like a table caption, which is the volume's own
    # index of what it crosses with what.
    captions = sorted({" ".join(m.group(0).split())
                       for page in pages
                       for m in re.finditer(r"Table\s+[\dA-Z][\d.\-A-Z]*\s*:?[^\n]{0,140}",
                                            page)})
    log(f"  {len(captions)} distinct table captions:")
    for cap in captions:
        log(f"    {cap[:170]}")


# ---------------------------------------------------------------------------
# --routes x: the routes left after the national report proved to hold no
# provincial cross -- the office's own file store, its statistics portal, the
# 2005 volume, and the survey.
# ---------------------------------------------------------------------------

WP_HOST = "https://www.lsb.gov.la"
PORTALS = [
    "https://laosis.lsb.gov.la/",
    "https://laosis.lsb.gov.la/tabulation/public/",
    "http://laosis.lsb.gov.la/",
    "https://www.decide.la/",
    "http://www.decide.la/",
    "https://decide.la/",
]
PDFS_2005 = [
    "https://data.opendevelopmentmekong.net/dataset/af8f9e99-8d9b-484b-9301-"
    "321da2051ae7/resource/9f24c10c-6234-47fe-a7c7-409c5dea994d/download",
    "https://data.opendevelopmentmekong.net/dataset/126050ca-c1b1-4fd9-a6f4-"
    "53b9c499ca87/resource/f54fadc4-8dca-4c0a-a9a8-a6a12f88657c/download",
]
UNFPA_PAGES = [f"https://lao.unfpa.org/en/publications?page={n}" for n in range(0, 6)]
ODM_QUERIES = ["Lao population census 2015", "census 2015 ethnic", "LSIS",
               "Lao social indicator survey", "population province Laos"]


def probe_wordpress() -> None:
    """The office's site is WordPress, so its own REST API lists every file it
    has ever uploaded -- which no link on the rendered page has to point at."""
    log("== route (x): lsb.gov.la's own file store, through the WordPress API")
    for page in range(1, 8):
        url = f"{WP_HOST}/wp-json/wp/v2/media?per_page=100&page={page}"
        body = get(url, limit=4_000_000)
        if not body:
            break
        try:
            items = json.loads(body)
        except json.JSONDecodeError:
            log(f"      not JSON: {' '.join(body[:200].split())!r}")
            break
        if not isinstance(items, list) or not items:
            break
        log(f"  page {page}: {len(items)} item(s)")
        for item in items:
            src = str(item.get("source_url", ""))
            if re.search(r"\.(pdf|xlsx?|csv|zip)$", src, re.IGNORECASE):
                title = (item.get("title") or {}).get("rendered", "")
                log(f"    {str(item.get('date', ''))[:10]}  {src[:150]}")
                log(f"        {' '.join(str(title).split())[:140]}")
        if len(items) < 100:
            break


def probe_portals() -> None:
    log("== route (x): the statistics portals")
    for url in PORTALS:
        get(url, limit=4000)
    log("  -- laosis with the intermediate certificate its server omits")
    for url in ("https://laosis.lsb.gov.la/", "https://laosis.lsb.gov.la/tabulation/public/"):
        try:
            body = http_get(url, cache=False, retries=0, timeout=60, aia=True)
            assert isinstance(body, str)
            log(f"  aia 200 {len(body):>8}  {url}")
            log(f"      {' '.join(body[:600].split())}")
        except Exception as exc:  # noqa: BLE001
            log(f"  aia !! {type(exc).__name__}: {str(exc)[:140]}  {url}")


def probe_unfpa() -> None:
    log("== route (x): every page of UNFPA Laos's publication list")
    seen: set[str] = set()
    for url in UNFPA_PAGES:
        body = get(url)
        if not body:
            continue
        for href in sorted(set(re.findall(r'href="([^"]+)"', body))):
            if "/publications/" in href and href not in seen:
                seen.add(href)
                log(f"    {href[:160]}")


def probe_odm() -> None:
    log("== route (x): Open Development Laos, by phrase")
    for query in ODM_QUERIES:
        url = ("https://data.laos.opendevelopmentmekong.net/api/3/action/package_search?"
               + urllib.parse.urlencode({"q": query, "rows": "15"}))
        body = get(url, limit=2_000_000)
        if not body:
            continue
        try:
            result = json.loads(body).get("result", {})
        except json.JSONDecodeError:
            continue
        log(f"  {query!r}: {result.get('count', 0)} dataset(s)")
        for pkg in result.get("results", [])[:15]:
            log(f"    {str(pkg.get('name', ''))[:70]:70} {str(pkg.get('title', ''))[:70]}")
            for res in pkg.get("resources", [])[:6]:
                log(f"        {str(res.get('format', '?')):8} {str(res.get('url', ''))[:120]}")


def probe_2005() -> None:
    log("== route (x): the 2005 volume")
    for url in PDFS_2005:
        head(url)


ODM_DATASETS = [
    "lao-population-and-housing-census-2015-general-demographic",
    "iv-2015", "4-2015", "socioeconomic-atlas-of-the-lao-pdr-2015",
    "population-census-lao-pdr-20051",
    "census-results-in-brief-laos-population-census-2005-and-1995",
    "lsis-ii-2017", "lao-social-indicator-survey-ii-201718",
    "lao-population-and-education-2019", "ethnic-family-of-lao-pdr",
]


def probe_datasets() -> None:
    """Every resource of the datasets the phrase search named, whole: a CKAN
    listing truncates a URL and a truncated URL cannot be fetched."""
    log("== route (d): Open Development Laos, dataset by dataset")
    for name in ODM_DATASETS:
        url = ("https://data.laos.opendevelopmentmekong.net/api/3/action/package_show?"
               + urllib.parse.urlencode({"id": name}))
        body = get(url, limit=4_000_000)
        if not body:
            continue
        try:
            pkg = json.loads(body).get("result") or {}
        except json.JSONDecodeError:
            log("      not JSON")
            continue
        log(f"  == {name}: {str(pkg.get('title', ''))[:100]}")
        notes = " ".join(str(pkg.get("notes") or "").split())
        if notes:
            log(f"     notes: {notes[:500]}")
        for res in pkg.get("resources", []):
            log(f"     {str(res.get('format', '?')):9} {str(res.get('name', ''))[:70]}")
            log(f"         {res.get('url', '')}")
            if res.get("datastore_active"):
                log(f"         datastore_active, id {res.get('id')}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--routes", default="afhw",
                    help="a (pages), f (candidate files), h (HDX), w (Wikipedia), "
                         "p (scan the census volume)")
    ap.add_argument("--rows", type=int, default=3)
    ap.add_argument("--contents", default="",
                    help="with route p: page numbers to print whole")
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
    if "p" in args.routes:
        probe_volume(args.rows, args.contents)
    if "d" in args.routes:
        probe_datasets()
    if "x" in args.routes:
        probe_wordpress()
        probe_portals()
        probe_unfpa()
        probe_odm()
        probe_2005()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
