#!/usr/bin/env python3
"""Read-only probes for religion by municipality in Sweden and Finland.

Gap round 2, item A: the Church of Sweden's and the Evangelical Lutheran
Church of Finland's membership by municipality, and first of all whether
Statistics Finland -- or the register keeper, DVV -- publishes the population
register's religious community by region, which would be a count of everyone
and beat any one church's figures. The sandbox cannot reach these hosts, so
the runner asks and prints only what a decision needs.

    python -m scripts.fetch_census.church_probe --run c1_fin_search,c1_swe_cdx

Nothing is written; the output is the log. The generic readers (PxWeb,
Wayback CDX, links, workbooks, PDFs) are nordic_probe's.
"""

from __future__ import annotations

import argparse
import re
import time
import urllib.parse
from collections import defaultdict
from typing import Any

from .nordic_probe import (cdx, fetch, get_json, links, pdf, pdf_heads,  # noqa: F401
                           px_meta, px_search, xlsx)

STATFIN_FI = "https://pxdata.stat.fi/PxWeb/api/v1/fi/StatFin"
PASSIIVI_FI = "https://pxdata.stat.fi/PxWeb/api/v1/fi/StatFin_Passiivi"
CLASS = ("https://data.stat.fi/api/classifications/v2/correspondenceTables/"
         "{src}_1_{y}0101%23{tgt}_1_{y}0101/maps?content=data&meta=max&lang=fi")
SVK = "https://www.svenskakyrkan.se/filer/1374643/"
EVL = "https://www.kirkontilastot.fi/"


def searches(base: str, queries: list[str], limit: int = 25) -> None:
    """A PxWeb database searched for each query in turn."""
    for q in queries:
        print(f"  -- {base.rsplit('/', 1)[-1]} ?query={q}")
        try:
            px_search(f"{base}?query={urllib.parse.quote(q)}", limit=limit)
        except Exception as exc:                  # a failed search is its answer
            print(f"    FAILED {exc.__class__.__name__}: {str(exc)[:200]}")
        time.sleep(1.5)


def ckan(base: str, queries: list[str], rows: int = 12) -> None:
    """A CKAN portal's datasets for each query: title, publisher, resources."""
    for q in queries:
        url = f"{base}/api/3/action/package_search?q={urllib.parse.quote(q)}&rows={rows}"
        try:
            body = get_json(url)
        except Exception as exc:
            print(f"  {q}: FAILED {exc.__class__.__name__}: {str(exc)[:200]}")
            continue
        result = body.get("result", {})
        print(f"  {q}: {result.get('count')} datasets")
        for pkg in result.get("results", [])[:rows]:
            org = (pkg.get("organization") or {}).get("title")
            print(f"    {pkg.get('name')} | {pkg.get('title')} | {org}")
            for res in (pkg.get("resources") or [])[:6]:
                print(f"      - {res.get('format')} {res.get('name')} -> {res.get('url')}")


def heads(urls: list[str]) -> None:
    """Each URL's outcome: size and first bytes, or the HTTP error."""
    for url in urls:
        try:
            raw = fetch(url, accept="*/*")
            print(f"  {url[-90:]}: {len(raw):,} bytes, starts {raw[:4]!r}")
        except Exception as exc:
            print(f"  {url[-90:]}: {str(exc)[:110]}")
        time.sleep(1.0)


def snippets(url: str, pattern: str, width: int = 160, limit: int = 30) -> None:
    """The text around each match of ``pattern`` in a page."""
    raw = fetch(url, accept="text/html,*/*").decode("utf-8", "replace")
    hits = [m.start() for m in re.finditer(pattern, raw, re.I)]
    print(f"  {len(raw):,} characters, {len(hits)} matches of /{pattern}/")
    for at in hits[:limit]:
        print("    ..." + " ".join(raw[max(0, at - width):at + width].split()) + "...")


def correspondence(src: str, tgt: str, year: int) -> None:
    """A classification key, compactly: each target and the sources in it."""
    body = get_json(CLASS.format(src=src, tgt=tgt, y=year))
    groups: dict[str, list[str]] = defaultdict(list)
    names: dict[str, str] = {}
    for entry in body:
        s, t = entry["sourceItem"], entry["targetItem"]
        sname = (s.get("classificationItemNames") or [{}])[0].get("name", "")
        tname = (t.get("classificationItemNames") or [{}])[0].get("name", "")
        groups[t["code"]].append(f"{s['code']} {sname}")
        names[t["code"]] = tname
    print(f"  {src}->{tgt} {year}: {len(body)} maps into {len(groups)} targets")
    for code in sorted(groups):
        print(f"    {code} {names[code]}: {'; '.join(sorted(groups[code]))}")


def kolada(queries: list[str]) -> None:
    """Kolada's KPIs whose title matches each query."""
    for q in queries:
        body = get_json(f"https://api.kolada.se/v2/kpi?title={urllib.parse.quote(q)}")
        values = body.get("values", [])
        print(f"  {q}: {len(values)} KPIs")
        for kpi in values[:40]:
            print(f"    {kpi.get('id')} | {kpi.get('title')} | {kpi.get('municipality_type')} | "
                  f"{kpi.get('publ_period')} | {str(kpi.get('description'))[:160]}")


PROBES: dict[str, Any] = {
    # Round c1. Finland: is the register's religious community published by
    # region anywhere -- StatFin, its archive, DVV, the open-data portal?
    "c1_fin_search": lambda: searches(STATFIN_FI, ["uskonnollinen", "uskontokunta", "uskonto",
                                                   "kirkkoon kuuluvat", "evankelis"]),
    "c1_fin_passiivi": lambda: searches(PASSIIVI_FI, ["uskonnollinen", "uskontokunta",
                                                      "uskonto", "kirkko"]),
    "c1_fin_11rx": lambda: px_meta(f"{STATFIN_FI}/vaerak/11rx.px",
                                   allvals=r"(?i)(?!timeperiod|vuosi|ika|sukupuoli).*"),
    "c1_fin_11ra": lambda: px_meta(f"{STATFIN_FI}/vaerak/11ra.px",
                                   grep=r"^(KU091|SK011|MK01|SSS) ",
                                   allvals=r"(?i)contentscode|tiedot"),
    "c1_fin_dvv_cdx": lambda: cdx(
        "url=dvv.fi/documents/*&filter=original:.*(?:[Uu]sko|[Rr]eligi|[Tt]rossamf|"
        "[Kk]irkkoon|[Jj]%C3%A4sen).*", limit=200),
    "c1_fin_avoindata": lambda: ckan("https://www.avoindata.fi/data",
                                     ["uskontokunta", "uskonnollinen yhdyskunta",
                                      "kirkkoon kuuluminen", "seurakunta jäsenmäärä"]),
    "c1_fin_evl_viz": lambda: snippets(f"{EVL}viz.php?id=311",
                                       r"tableau|views/|embed|\.csv|\.xlsx"),
    "c1_fin_evl_index": lambda: links(EVL, r"viz\.php|tiedostot|xlsx|jäsen|j%C3%A4sen|kunn",
                                      limit=120),
    "c1_fin_evl_live": lambda: heads(
        [f"{EVL}tiedostot/J%C3%A4senm%C3%A4%C3%A4r%C3%A4{y}.xlsx" for y in range(2021, 2026)]),
    "c1_fin_ort_cdx": lambda: cdx(
        "url=ort.fi/*&filter=original:.*(?:xlsx|xls|pdf).*&filter=original:.*(?:[Jj]%C3%A4sen|"
        "[Jj]asen|[Tt]ilasto).*", limit=120),
    "c1_fin_sk_mk": lambda: correspondence("seutukunta", "maakunta", 2020),
    "c1_fin_sk_mk_2026": lambda: correspondence("seutukunta", "maakunta", 2026),
    # Sweden: a newer edition of the Church's table by kommun than 2021's, or
    # another publisher of the same count (Kolada).
    "c1_swe_cdx": lambda: cdx(
        "url=svenskakyrkan.se/filer/*&from=2022&filter=original:.*(?:[Ff]olkm|[Nn]yckeltal|LKF|"
        "[Mm]edlemsutv|[Kk]ommun%20och|per%20kommun).*", limit=300),
    "c1_swe_page": lambda: links("https://www.svenskakyrkan.se/statistik", r".", limit=200),
    "c1_swe_kolada": lambda: kolada(["kyrkan", "Svenska kyrkan", "medlem", "trossamfund"]),
    "c1_swe_2021": lambda: pdf_heads([SVK + "NyckeltalLKF(1).pdf", SVK + "NyckeltalLKF.pdf"]),
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True,
                    help="comma-separated probe names, or a prefix ending in '*'")
    args = ap.parse_args()
    names: list[str] = []
    for part in args.run.split(","):
        names += ([n for n in PROBES if n.startswith(part[:-1])] if part.endswith("*")
                  else [part])
    for name in names:
        print(f"== {name}")
        try:
            PROBES[name]()
        except Exception as exc:        # a probe's failure is its answer
            print(f"  FAILED: {exc.__class__.__name__}: {exc}"[:600])
        time.sleep(1.0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
