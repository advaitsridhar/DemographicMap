#!/usr/bin/env python3
"""Uruguay's 2023 census by department and municipio.

Draft: probes only, while INE's microdata catalogue is read.

Usage:
    python -m scripts.fetch_census.uruguay_census --probe microdata
"""

from __future__ import annotations

import argparse
import html
import http.cookiejar
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

from ._shared import log

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from probe_tls import completed_context  # noqa: E402

ANDA = "https://www4.ine.gub.uy/Anda5/index.php/catalog/781"
HEADERS = {"User-Agent": "DemographicMap/1.0 (+https://github.com/advaitsridhar/DemographicMap)"}


def opener() -> urllib.request.OpenerDirector:
    """Cookies kept, and INE's certificate chain completed from its AIA (still verified)."""
    ctx, _ = completed_context(urllib.parse.urlsplit(ANDA).hostname or "")
    return urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx),
                                       urllib.request.HTTPCookieProcessor(
                                           http.cookiejar.CookieJar()))


def fetch(open_: urllib.request.OpenerDirector, url: str, data: dict | None = None,
          limit: int | None = None) -> tuple[bytes, dict]:
    body = urllib.parse.urlencode(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, headers=HEADERS)
    with open_.open(req, timeout=300) as resp:
        return (resp.read(limit) if limit else resp.read()), dict(resp.headers)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--probe", choices=["microdata", "file"])
    ap.add_argument("--url", help="with --probe file: the file to read the head of")
    args = ap.parse_args()
    open_ = opener()
    if args.probe == "microdata":
        page, _ = fetch(open_, f"{ANDA}/get-microdata")
        page, headers = fetch(open_, f"{ANDA}/get-microdata", {"accept": "Aceptar"})
        text = page.decode("utf-8", "replace")
        print(f"after accepting: {len(text):,} characters, {headers.get('Content-Type')}")
        for href, label in re.findall(r'(?is)<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', text):
            label = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", label))).strip()
            if "download" in href or "Descarg" in label:
                print(f"  {label[:100]!r} -> {href}")
        for chunk in re.findall(r"(?is)(?:[A-Za-z_]+\.(?:csv|zip|rar|sav|dta|RData|parquet))"
                                r"[^<]{0,120}", text):
            print(f"  file mention: {chunk[:160]!r}")
        return 0
    if args.probe == "file":
        page, _ = fetch(open_, f"{ANDA}/get-microdata")
        fetch(open_, f"{ANDA}/get-microdata", {"accept": "Aceptar"})
        head, headers = fetch(open_, args.url, limit=4000)
        print({k: v for k, v in headers.items() if k.lower() in
               ("content-type", "content-length", "content-disposition")})
        print(repr(head[:3000]))
        return 0
    log("uruguay_census: nothing but probes yet")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
