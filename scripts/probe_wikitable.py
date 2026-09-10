#!/usr/bin/env python3
"""Print the wikitables of a Wikipedia article, compactly, to see what a table holds.

The MediaWiki API returns an article's wikitext; the tables inside it are what
this project might read (Thailand's provincial religion came from one). Dumping
the whole article into a runner log to find out is wasteful, so this prints
each table's rows with links, refs and styling stripped, one row per line,
cells separated by " | ", and only the first N rows of each.

Usage:
    python -m scripts.probe_wikitable "Religion in Cambodia" --rows 40
    python -m scripts.probe_wikitable "Religion in Kazakhstan" --table 1 --rows 60
"""

from __future__ import annotations

import argparse
import re
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import http_json, log  # noqa: E402

API = "https://en.wikipedia.org/w/api.php"
LINK = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]*))?\]\]")
REF = re.compile(r"<ref[^>]*/>|<ref[^>]*>.*?</ref>", re.S)
TEMPLATE = re.compile(r"\{\{[^{}]*\}\}")
TAG = re.compile(r"<[^>]+>")
ATTR = re.compile(r'^[^|]*(?:style|rowspan|colspan|scope|align|width|bgcolor|class)="[^"]*"[^|]*\|')


def plain(cell: str) -> str:
    cell = REF.sub("", cell)
    for _ in range(3):
        cell = TEMPLATE.sub(lambda m: m.group(0)[2:-2].split("|")[-1], cell)
    cell = LINK.sub(lambda m: m.group(2) if m.group(2) is not None else m.group(1), cell)
    cell = TAG.sub(" ", cell).replace("'''", "").replace("''", "")
    cell = ATTR.sub("", cell.strip())
    return " ".join(cell.split())


def tables(wikitext: str) -> list[list[list[str]]]:
    out: list[list[list[str]]] = []
    depth, current, rows = 0, None, None
    for line in wikitext.split("\n"):
        s = line.strip()
        if s.startswith("{|"):
            depth += 1
            if depth == 1:
                rows = []
            continue
        if s.startswith("|}"):
            depth -= 1
            if depth == 0 and rows is not None:
                out.append(rows)
                rows = None
            continue
        if depth != 1 or rows is None:
            continue
        if s.startswith("|-") or s.startswith("|+"):
            if s.startswith("|-"):
                rows.append([])
            continue
        if s.startswith("!") or s.startswith("|"):
            marker = s[0]
            cells = re.split(r"!!|\|\|", s[1:]) if marker == "!" else s[1:].split("||")
            if not rows:
                rows.append([])
            rows[-1].extend(plain(c) for c in cells)
    return [[r for r in t if r] for t in out]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("title")
    ap.add_argument("--rows", type=int, default=30)
    ap.add_argument("--table", type=int, default=0, help="1-based; 0 means every table")
    ap.add_argument("--width", type=int, default=32, help="characters per cell")
    args = ap.parse_args()

    q = urllib.parse.urlencode({"action": "parse", "page": args.title, "prop": "wikitext",
                                "format": "json", "formatversion": "2", "redirects": "1"})
    data = http_json(f"{API}?{q}", timeout=90)
    parsed = data.get("parse") or {}
    wikitext = parsed.get("wikitext") or ""
    log(f"page: {parsed.get('title')!r}, {len(wikitext):,} bytes of wikitext")
    found = tables(wikitext)
    log(f"  {len(found)} table(s)")
    for i, t in enumerate(found, 1):
        if args.table and i != args.table:
            continue
        log(f"\n--- table {i}: {len(t)} rows ---")
        for row in t[:args.rows]:
            log("  " + " | ".join(c[:args.width] for c in row))
        if len(t) > args.rows:
            log(f"  ... {len(t) - args.rows} more rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
