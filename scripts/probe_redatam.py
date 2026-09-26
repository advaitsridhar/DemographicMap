#!/usr/bin/env python3
"""What a REDATAM WebServer offers, before a reader is written against it.

CELADE's REDATAM WebServer is how several Latin American offices publish a
census for on-line tabulation: INEI's 2017 census of Peru among them, as the
public base CPV2017DI. Its portal is a frameset whose panes are temporary
pages written for the session (``RpWebUtilities.exe/Text?LFN=...``), and the
tabulation forms -- frequencies, crosstabs, the variables each offers and the
geographic breaks -- are in those panes, not in the portal page itself.

This opens the portal, reads every pane in the same session, and prints the
pane's text, its links, and each form's action and fields (with a select's
options), following links whose text matches ``--follow`` one level down.
Nothing is written; the output is the log.

Usage:
    python -m scripts.probe_redatam "https://censos2017.inei.gob.pe/bininei/RpWebEngine.exe/Portal?BASE=CPV2017DI&lang=esp"
    python -m scripts.probe_redatam URL --follow Frecuencia,Cruce,Promedio
"""

from __future__ import annotations

import argparse
import html
import http.cookiejar
import re
import urllib.parse
import urllib.request

HEADERS = {"User-Agent": "DemographicMap/1.0 (+https://github.com/advaitsridhar/DemographicMap)"}


class Session:
    def __init__(self) -> None:
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def get(self, url: str, data: bytes | None = None) -> str:
        req = urllib.request.Request(url, data=data, headers=HEADERS)
        with self.opener.open(req, timeout=90) as resp:
            raw = resp.read()
            charset = resp.headers.get_content_charset() or "utf-8"
        return raw.decode(charset, "replace")


def text_of(page: str) -> str:
    page = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", page)
    page = re.sub(r"(?s)<[^>]+>", " ", page)
    return re.sub(r"\s+", " ", html.unescape(page)).strip()


def attrs(tag: str) -> dict[str, str]:
    return {k.lower(): html.unescape(v) for k, v in
            re.findall(r'([a-zA-Z_:-]+)\s*=\s*["\']([^"\']*)["\']', tag)}


def report(base: str, page: str, limit: int) -> list[tuple[str, str]]:
    """Print a pane's text, frames, links and forms; return its (link text, url)s."""
    print(f"  text: {text_of(page)[:limit]}")
    for tag in re.findall(r"(?is)<i?frame\b[^>]*>", page):
        src = attrs(tag).get("src")
        if src:
            print(f"  frame: {urllib.parse.urljoin(base, src)}")
    links = []
    for href, label in re.findall(r'(?is)<a\b[^>]*href\s*=\s*["\']([^"\']+)["\'][^>]*>(.*?)</a>', page):
        url = urllib.parse.urljoin(base, html.unescape(href))
        links.append((text_of(label), url))
    for label, url in links[:120]:
        print(f"  link: {label[:60]!r} -> {url}")
    for form in re.findall(r"(?is)<form\b.*?</form>", page):
        head = attrs(re.match(r"(?is)<form\b[^>]*>", form).group(0))
        print(f"  form: {head.get('method', 'get').upper()} "
              f"{urllib.parse.urljoin(base, head.get('action', ''))}")
        for tag in re.findall(r"(?is)<input\b[^>]*>", form):
            a = attrs(tag)
            print(f"    input {a.get('type', 'text')} {a.get('name')!r} = {a.get('value', '')[:80]!r}")
        for name, body in re.findall(r'(?is)<select\b[^>]*name\s*=\s*["\']([^"\']+)["\'][^>]*>(.*?)</select>', form):
            options = re.findall(r'(?is)<option\b[^>]*value\s*=\s*["\']([^"\']*)["\'][^>]*>(.*?)</option>', body)
            print(f"    select {name!r}: {len(options)} options: "
                  + "; ".join(f"{v}={text_of(t)[:40]}" for v, t in options[:60]))
        for name in re.findall(r'(?is)<textarea\b[^>]*name\s*=\s*["\']([^"\']+)["\']', form):
            print(f"    textarea {name!r}")
    return links


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("url")
    ap.add_argument("--follow", default="",
                    help="comma-separated words; links whose text contains one are opened")
    ap.add_argument("--limit", type=int, default=1500, help="characters of each pane's text")
    args = ap.parse_args()
    session = Session()
    print(f"page: {args.url}")
    portal = session.get(args.url)
    links = report(args.url, portal, args.limit)
    frames = [urllib.parse.urljoin(args.url, attrs(t).get("src", ""))
              for t in re.findall(r"(?is)<i?frame\b[^>]*>", portal) if attrs(t).get("src")]
    words = [w.strip().lower() for w in args.follow.split(",") if w.strip()]
    for frame in frames:
        print(f"pane: {frame}")
        try:
            links += report(frame, session.get(frame), args.limit)
        except Exception as exc:                      # noqa: BLE001 -- the log is the product
            print(f"  unreadable: {type(exc).__name__}: {exc}")
    seen = set()
    for label, url in links:
        if not words or url in seen or not any(w in label.lower() for w in words):
            continue
        seen.add(url)
        print(f"follow: {label!r} -> {url}")
        try:
            report(url, session.get(url), args.limit)
        except Exception as exc:                      # noqa: BLE001
            print(f"  unreadable: {type(exc).__name__}: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
