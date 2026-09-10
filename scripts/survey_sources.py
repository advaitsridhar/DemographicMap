#!/usr/bin/env python3
"""Measure candidate sources with a real network: URLs and Wikipedia articles.

The research agents that propose sources for a country can search the web but
cannot open a page, and the build sandbox cannot reach any statistical host at
all. This is the step that runs where the network is -- a GitHub runner -- and
turns each proposal into a measurement:

* every candidate URL a finding names is requested, and what came back is
  recorded: status, content type, size, and for a PDF its page count, for a
  workbook its sheet names, for a CSV its header row, for JSON its top-level
  keys. A 404 here is a fact about that URL.
* Wikipedia is sampled rather than assumed. For each country a handful of
  second-level shape names are looked up through the MediaWiki search API, the
  article's wikitext is read, and the signals that mean "this article carries a
  demographic composition" are counted: an infobox with religion / ethnic /
  language parameters, a Religion or Demographics section holding a wikitable,
  a {{Pie chart}} or {{bar box}} of shares. The country-level list articles the
  agents found are read the same way. What is reported is whether the articles
  are worth an adapter, never the figures themselves -- those would have to be
  read by an adapter that states its source and its year like every other.

Nothing is written into data/. Findings go to data/survey/<ISO3>.json for a
person to read, and the log carries a one-line verdict per country.

Usage:
    python scripts/survey_sources.py --findings survey/findings --packets survey/packets \\
        --countries KEN,TZA --out data/survey
"""

from __future__ import annotations

import argparse
import gzip
import io
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

AGENT = ("DemographicMap-survey/1.0 (https://github.com/advaitsridhar/DemographicMap; "
         "census@demographicmap.invalid) python-urllib")
WIKI_API = "https://en.wikipedia.org/w/api.php"
HEAD_BYTES = 256 * 1024

# What in an article's wikitext says "there is a composition here". Each is a
# signal, not a verdict: a Religion section with prose and no table is not one.
INFOBOX_PARAMS = re.compile(
    r"^\s*\|\s*(religion|religions|ethnic_groups?|ethnicity|languages?|"
    r"official_languages?|demographics\d?_(title|info\d+)|blank\d?_name)\s*=",
    re.I | re.M)
SECTION = re.compile(r"^==+\s*(Religion|Religions|Demographics?|Ethnic[^=]*|"
                     r"Languages?|Population)\s*==+", re.I | re.M)
TABLE = re.compile(r"\{\|\s*class=\"[^\"]*wikitable")
CHART = re.compile(r"\{\{\s*(Pie chart|bar box|bar percent|Historical populations)", re.I)
COMPOSITION_WORDS = re.compile(r"\b(Hindu|Muslim|Christian|Catholic|Buddhist|Sikh|"
                               r"Orthodox|Protestant|Sunni|Shia|Animis|Tradition|"
                               r"speakers?|mother tongue|ethnic)\b", re.I)


def get(url: str, *, timeout: int = 60, limit: int | None = HEAD_BYTES) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": AGENT,
                                               "Accept": "*/*"})
    out: dict[str, Any] = {"url": url}
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            out["status"] = r.status
            out["content_type"] = r.headers.get("Content-Type", "")
            out["content_length"] = r.headers.get("Content-Length")
            out["final_url"] = r.geturl()
            body = r.read(limit) if limit else r.read()
            # Some hosts (IBGE's API among them) gzip the body unasked; a
            # gzip magic number is not a file kind, so undo it here.
            if body[:2] == b"\x1f\x8b":
                try:
                    body = gzip.decompress(body)
                except Exception:                            # noqa: BLE001 -- truncated
                    pass                        # a partial read cannot be inflated
            out["body"] = body
    except urllib.error.HTTPError as err:
        out["status"] = err.code
        out["body"] = err.read(2000)
    except Exception as err:                                  # noqa: BLE001 -- reported
        out["status"] = 0
        out["error"] = f"{type(err).__name__}: {err}"
        out["body"] = b""
    return out


def describe_body(res: dict[str, Any]) -> dict[str, Any]:
    """What kind of thing answered, from the first bytes."""
    body: bytes = res.get("body") or b""
    ctype = (res.get("content_type") or "").lower()
    d: dict[str, Any] = {"bytes_read": len(body)}
    head = body[:4]
    if head == b"%PDF":
        d["kind"] = "pdf"
        m = re.search(rb"/Count\s+(\d+)", body)
        if m:
            d["pages_hint"] = int(m.group(1))
    elif head[:2] == b"PK":
        d["kind"] = "zip/xlsx"
        try:
            full = res["body"] if len(body) < HEAD_BYTES else get(res["url"], limit=None)["body"]
            with zipfile.ZipFile(io.BytesIO(full)) as z:
                names = z.namelist()
                d["members"] = names[:12]
                if "xl/workbook.xml" in names:
                    wb = z.read("xl/workbook.xml").decode("utf-8", "replace")
                    d["sheets"] = re.findall(r'<sheet [^>]*name="([^"]+)"', wb)[:20]
        except Exception as err:                             # noqa: BLE001 -- reported
            d["zip_error"] = f"{type(err).__name__}: {err}"
    else:
        text = body.decode("utf-8", "replace")
        stripped = text.lstrip()
        if stripped.startswith(("{", "[")):
            d["kind"] = "json"
            try:
                parsed = json.loads(text) if len(body) < HEAD_BYTES else None
                if isinstance(parsed, dict):
                    d["keys"] = list(parsed)[:15]
                elif isinstance(parsed, list):
                    d["items"] = len(parsed)
            except ValueError:
                d["json_note"] = "truncated or invalid at 256 KB"
        elif "html" in ctype or stripped[:15].lower().startswith(("<!doctype", "<html")):
            d["kind"] = "html"
            title = re.search(r"<title[^>]*>(.*?)</title>", text, re.I | re.S)
            d["title"] = " ".join(title.group(1).split())[:160] if title else None
            d["links_to_files"] = sorted(set(
                m for m in re.findall(r'href="([^"]+\.(?:csv|xlsx?|pdf|zip|json))', text, re.I)))[:25]
            d["mentions"] = sorted(set(w.lower() for w in re.findall(
                r"\b(religion|ethnic\w*|language\w*|mother tongue|census)\b", text, re.I)))
        else:
            d["kind"] = "text/csv?"
            lines = text.splitlines()
            d["first_lines"] = [ln[:200] for ln in lines[:3]]
    return d


def wiki(params: dict[str, str]) -> dict[str, Any]:
    q = dict(params, format="json", maxlag="5")
    url = f"{WIKI_API}?{urllib.parse.urlencode(q)}"
    res = get(url, limit=None)
    time.sleep(0.25)
    if res.get("status") != 200:
        return {"error": res.get("status"), "url": url}
    try:
        return json.loads(res["body"])
    except ValueError:
        return {"error": "not json", "url": url}


def wiki_search(query: str) -> dict[str, Any] | None:
    r = wiki({"action": "query", "list": "search", "srsearch": query, "srlimit": "1"})
    hits = (r.get("query") or {}).get("search") or []
    return hits[0] if hits else None


def wiki_text(title: str) -> str | None:
    r = wiki({"action": "parse", "page": title, "prop": "wikitext", "redirects": "1"})
    return ((r.get("parse") or {}).get("wikitext") or {}).get("*")


def signals(text: str) -> dict[str, Any]:
    """Count what in a page says composition, and where."""
    out: dict[str, Any] = {
        "infobox_params": sorted({m.group(1).lower() for m in INFOBOX_PARAMS.finditer(text)}),
        "sections": [m.group(1).strip() for m in SECTION.finditer(text)],
        "wikitables": len(TABLE.findall(text)),
        "charts": sorted({m.group(1) for m in CHART.finditer(text)}),
    }
    # A table or chart inside a relevant section is the strong signal.
    strong = 0
    for m in SECTION.finditer(text):
        start = m.end()
        nxt = re.search(r"^==[^=]", text[start:], re.M)
        block = text[start: start + (nxt.start() if nxt else len(text))]
        if TABLE.search(block) or CHART.search(block):
            if COMPOSITION_WORDS.search(block):
                strong += 1
    out["composition_blocks"] = strong
    out["verdict"] = ("composition" if strong else
                      "infobox-only" if any(p.startswith(("religion", "ethnic", "language"))
                                            for p in out["infobox_params"]) else
                      "none")
    return out


def sample_wikipedia(name: str, country: str) -> dict[str, Any]:
    hit = wiki_search(f'"{name}" {country}')
    if not hit:
        hit = wiki_search(f"{name} {country}")
    if not hit:
        return {"shape_name": name, "found": False}
    text = wiki_text(hit["title"]) or ""
    out = {"shape_name": name, "found": True, "title": hit["title"],
           "url": "https://en.wikipedia.org/wiki/" + urllib.parse.quote(hit["title"].replace(" ", "_")),
           "wikitext_bytes": len(text)}
    out.update(signals(text))
    return out


HDX_SEARCH = "https://data.humdata.org/api/3/action/package_search"
CRAWL_WORDS = re.compile(r"census|religio|ethnic|tribe|caste|language|mother.?tongue|"
                         r"population|demograph|recensement|censo|religi[oó]n|etnia|"
                         r"lengua|idioma|zensus|nüfus|sensus|agama|suku|bahasa", re.I)
FILE_EXT = re.compile(r"\.(csv|xlsx?|pdf|zip|json|ods)(\?|$)", re.I)


def hdx_search(country: str, iso3: str) -> list[dict[str, Any]]:
    """What HDX holds for this country that names a field this map wants.

    HDX is a CKAN, and CKAN has a real search API -- no page, no budget, one
    call per query. Six of this map's countries are already read from it (the
    US Census Bureau's international series, DHS-derived tables), so it is the
    first door to try everywhere rather than a fallback.
    """
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for term in ("religion", "ethnicity", "language", "census"):
        q = urllib.parse.urlencode({"q": f"{term} {country}", "rows": "10",
                                    "fq": f"groups:{iso3.lower()}"})
        res = get(f"{HDX_SEARCH}?{q}", limit=None)
        if res.get("status") != 200:
            out.append({"term": term, "error": res.get("status") or res.get("error")})
            continue
        try:
            payload = json.loads(res["body"])
        except ValueError:
            continue
        for ds in (payload.get("result") or {}).get("results") or []:
            name = ds.get("name")
            if not name or name in seen:
                continue
            seen.add(name)
            resources = [{"name": r.get("name"), "format": r.get("format"),
                          "url": r.get("url")} for r in (ds.get("resources") or [])[:8]]
            out.append({"term": term, "title": ds.get("title"), "name": name,
                        "org": (ds.get("organization") or {}).get("title"),
                        "url": f"https://data.humdata.org/dataset/{name}",
                        "resources": resources})
        time.sleep(0.3)
    return out


def crawl_nso(url: str, *, depth: int = 1, budget: int = 12) -> dict[str, Any]:
    """Follow an office's own links to the pages and files that name a field.

    One level deep and a dozen pages at most: enough to find a "Census 2022
    results" page and the files it links, not enough to be a nuisance. Every
    page is described the way a candidate URL is, so a 403, a bot wall or a
    broken certificate is recorded as such rather than read as absence.
    """
    home = get(url)
    out: dict[str, Any] = {"url": url, "status": home.get("status"),
                           "error": home.get("error"), "pages": []}
    if home.get("status") != 200:
        return out
    body = describe_body(home)
    out["title"] = body.get("title")
    text = (home.get("body") or b"").decode("utf-8", "replace")
    base = home.get("final_url") or url
    links: list[str] = []
    for href, label in re.findall(r'<a[^>]+href="([^"#]+)"[^>]*>(.*?)</a>', text, re.I | re.S):
        label = re.sub(r"<[^>]+>", " ", label)
        if CRAWL_WORDS.search(label) or CRAWL_WORDS.search(href):
            full = urllib.parse.urljoin(base, href)
            if urllib.parse.urlparse(full).netloc == urllib.parse.urlparse(base).netloc:
                if full not in links:
                    links.append(full)
    out["matching_links"] = len(links)
    for link in links[:budget]:
        res = get(link)
        entry: dict[str, Any] = {"url": link, "status": res.get("status")}
        if res.get("status") == 200:
            d = describe_body(res)
            entry["kind"] = d.get("kind")
            entry["title"] = d.get("title")
            entry["files"] = d.get("links_to_files")
            entry["mentions"] = d.get("mentions")
        else:
            entry["error"] = res.get("error")
        out["pages"].append(entry)
        time.sleep(0.5)
    return out


def table_headers(text: str) -> list[dict[str, Any]]:
    """Every wikitable's header cells, so a list article can be judged by
    whether one of its tables is a place-by-composition matrix."""
    out = []
    for m in TABLE.finditer(text):
        block = text[m.start(): m.start() + 3000]
        # A header row is "! a !! b !! c" on one line or "! a" per line; both
        # forms appear, sometimes in the same article.
        header = re.findall(r"^\s*!\s*(.+)$", block, re.M)[:14]
        cells = [re.sub(r"\[\[([^|\]]*\|)?([^\]]+)\]\]", r"\2", c).strip()
                 for line in header for c in line.split("!!")]
        place = any(re.search(r"\b(county|district|state|province|region|governorate|"
                              r"division|department|prefecture|municipality|zone)\b", c, re.I)
                    for c in cells)
        comp = sum(bool(COMPOSITION_WORDS.search(c)) for c in cells)
        rows = block.count("\n|-")
        out.append({"header": cells[:10], "place_column": place,
                    "composition_columns": comp, "rows_hint": rows})
    return out


def survey(iso3: str, finding: dict[str, Any], packet: dict[str, Any],
           *, wiki_samples: int) -> dict[str, Any]:
    out: dict[str, Any] = {"iso3": iso3, "name": packet.get("name"),
                           "tier_proposed": finding.get("tier"),
                           "sources": [], "wikipedia": {"list_articles": [], "admin2_samples": []}}
    for src in finding.get("subnational_sources") or []:
        url = src.get("url")
        if not url:
            continue
        res = get(url)
        entry = {k: src.get(k) for k in ("fields", "title", "kind", "format", "geography",
                                         "geography_count", "matches_boundary_level")}
        entry.update({"url": url, "status": res.get("status"),
                      "content_type": res.get("content_type"),
                      "final_url": res.get("final_url"), "error": res.get("error")})
        if res.get("status") == 200:
            entry["body"] = describe_body(res)
        out["sources"].append(entry)
        print(f"  {iso3} {res.get('status')} {(entry.get('body') or {}).get('kind', '-'):<9} {url[:100]}")

    country = packet.get("name") or iso3

    out["hdx"] = hdx_search(country, iso3)
    hdx_hits = [h for h in out["hdx"] if h.get("title")]
    print(f"  {iso3} hdx       {len(hdx_hits)} datasets")
    for h in hdx_hits[:6]:
        fmts = sorted({(r.get("format") or "?").upper() for r in h["resources"]})
        print(f"      [{h['term']}] {h['title'][:80]}  {fmts}")

    nso_url = (finding.get("nso") or {}).get("url") or packet.get("nso_url")
    if nso_url:
        out["nso_crawl"] = crawl_nso(nso_url)
        c = out["nso_crawl"]
        print(f"  {iso3} nso       {c.get('status')} {c.get('title') or c.get('error') or ''} "
              f"-> {c.get('matching_links', 0)} matching links, {len(c['pages'])} read")
        for pg in c["pages"]:
            if pg.get("files"):
                print(f"      {pg['status']} {pg.get('title', '')[:60]}: {len(pg['files'])} files")

    # List articles the agents named, plus the two titles that most often
    # carry a census table by first-level unit whether or not anyone named them.
    titles = [a.get("title") for a in (finding.get("wikipedia") or {}).get("country_list_articles") or []]
    for guess in (f"Religion in {country}", f"Demographics of {country}"):
        if guess not in titles:
            titles.append(guess)
    for title in titles:
        if not title:
            continue
        text = wiki_text(title) or ""
        e = {"title": title, "wikitext_bytes": len(text)}
        e.update(signals(text))
        e["tables"] = table_headers(text)
        e["place_by_composition_tables"] = sum(
            1 for tb in e["tables"] if tb["place_column"] and tb["composition_columns"] >= 2)
        out["wikipedia"]["list_articles"].append(e)
        print(f"  {iso3} wiki-list {e['verdict']:<12} tables={e['wikitables']} "
              f"place-by-composition={e['place_by_composition_tables']} {title}")

    names = (packet.get("admin2") or {}).get("sample_names") or []
    if not names:
        names = (packet.get("admin1") or {}).get("sample_names") or []
    for name in names[:wiki_samples]:
        e = sample_wikipedia(name, country)
        out["wikipedia"]["admin2_samples"].append(e)
        print(f"  {iso3} wiki-a2   {e.get('verdict', 'missing'):<12} {name} -> {e.get('title')}")

    got = [s for s in out["sources"] if s.get("status") == 200]
    comp = sum(1 for e in out["wikipedia"]["admin2_samples"] if e.get("verdict") == "composition")
    out["verdict"] = {
        "hdx_datasets": len(hdx_hits),
        "hdx_machine_readable": sum(1 for h in hdx_hits if any(
            (r.get("format") or "").upper() in ("CSV", "XLSX", "XLS", "JSON") for r in h["resources"])),
        "nso_files_found": sum(len(p.get("files") or []) for p in (out.get("nso_crawl") or {}).get("pages", [])),
        "wikipedia_list_tables_by_place": sum(e["place_by_composition_tables"]
                                              for e in out["wikipedia"]["list_articles"]),
        "urls_answering": f"{len(got)}/{len(out['sources'])}",
        "machine_readable": sorted({(s.get("body") or {}).get("kind") for s in got
                                    if (s.get("body") or {}).get("kind") in ("json", "zip/xlsx", "text/csv?")}),
        "wikipedia_admin2_with_composition": f"{comp}/{len(out['wikipedia']['admin2_samples'])}",
    }
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--findings", required=True)
    ap.add_argument("--packets", required=True)
    ap.add_argument("--countries", required=True, help="comma-separated ISO3, or ALL")
    ap.add_argument("--out", default="data/survey")
    ap.add_argument("--wiki-samples", type=int, default=5)
    args = ap.parse_args()

    findings = Path(args.findings); packets = Path(args.packets); out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    isos = ([p.stem for p in sorted(findings.glob("*.json"))] if args.countries == "ALL"
            else [c.strip().upper() for c in args.countries.split(",") if c.strip()])
    done = 0
    for iso in isos:
        f = findings / f"{iso}.json"; p = packets / f"{iso}.json"
        if not f.exists():
            print(f"{iso}: no finding file; skipped")
            continue
        finding = json.loads(f.read_text(encoding="utf-8"))
        packet = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
        print(f"== {iso} {packet.get('name', '')} (proposed tier {finding.get('tier')})")
        result = survey(iso, finding, packet, wiki_samples=args.wiki_samples)
        (out / f"{iso}.json").write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n",
                                          encoding="utf-8")
        v = result["verdict"]
        print(f"  {iso} VERDICT hdx {v['hdx_datasets']} ({v['hdx_machine_readable']} machine-readable) "
              f"nso-files {v['nso_files_found']} wiki-list-tables {v['wikipedia_list_tables_by_place']} "
              f"urls {v['urls_answering']} wiki-admin2 {v['wikipedia_admin2_with_composition']}")
        done += 1
    print(f"surveyed {done} countries")
    return 0


if __name__ == "__main__":
    sys.exit(main())
