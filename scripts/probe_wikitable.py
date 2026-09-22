#!/usr/bin/env python3
"""Print the wikitables of a Wikipedia article, compactly, to see what a table holds.

The MediaWiki API returns an article's wikitext; the tables inside it are what
this project might read (Thailand's provincial religion came from one). Dumping
the whole article into a runner log to find out is wasteful, so this prints
each table's rows with links, refs and styling stripped, one row per line,
cells separated by " | ", and only the first N rows of each.

A census table by region is often transcribed in the country's own Wikipedia
long before the English one, and sometimes only there, so the language edition
is an argument: ``--lang ro`` reads ro.wikipedia.org. ``--infobox`` prints the
first infobox's parameters instead of the tables, which is where a European
unit's article usually keeps whatever composition it has.

Usage:
    python -m scripts.probe_wikitable "Religion in Cambodia" --rows 40
    python -m scripts.probe_wikitable "Religion in Kazakhstan" --table 1 --rows 60
    python -m scripts.probe_wikitable --lang ro "Adamclisi, Constanta" --rows 40
    python -m scripts.probe_wikitable --lang bg --infobox "Област Благоевград"
"""

from __future__ import annotations

import argparse
import re
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import http_json, log  # noqa: E402

API = "https://{lang}.wikipedia.org/w/api.php"
LINK = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]*))?\]\]")
REF = re.compile(r"<ref[^>]*/>|<ref[^>]*>.*?</ref>", re.S)
TEMPLATE = re.compile(r"\{\{[^{}]*\}\}")
# A footnote is not part of the cell's text. Every other template is
# collapsed to whatever follows its last "|", which is right for {{lang}}
# and {{nowrap}} and wrong for this one: Taraclia's ethnic table labels a
# row "Moldovans{{efn|...an [[...|ongoing controversy]] regarding the ethnic
# identification of...}}", and collapsing that left the label reading
# "Moldovansongoing controversy]] regarding the ethnic identification of" --
# a label no reader has an entry for, which refused the whole table.
FOOTNOTE = re.compile(r"\{\{\s*(?:efn|sfn|refn|notetag|note label|ref label)\b"
                      r"[^{}]*\}\}", re.I)
TAG = re.compile(r"<[^>]+>")
ATTR = re.compile(r'^[^|]*(?:style|rowspan|colspan|scope|align|width|bgcolor|class)="[^"]*"[^|]*\|')


def plain(cell: str) -> str:
    cell = REF.sub("", cell)
    for _ in range(3):
        # Before the collapse below, and inside the loop: a footnote holding
        # a template of its own only looks like a footnote once that inner
        # template is gone.
        cell = FOOTNOTE.sub("", cell)
        cell = TEMPLATE.sub(lambda m: m.group(0)[2:-2].split("|")[-1], cell)
    cell = LINK.sub(lambda m: m.group(2) if m.group(2) is not None else m.group(1), cell)
    cell = TAG.sub(" ", cell).replace("'''", "").replace("''", "")
    cell = ATTR.sub("", cell.strip())
    return " ".join(cell.split())


def infobox_lines(wikitext: str) -> list[str]:
    """Top-level ``| key = value`` entries of the article's first infobox.

    A value runs until the next top-level parameter, so a multi-line list of
    faiths comes back as one entry.
    """
    out: list[str] = []
    depth = 0
    current: list[str] | None = None
    for line in wikitext.split("\n"):
        opened = line.count("{{")
        closed = line.count("}}")
        if depth == 1 and line.lstrip().startswith("|") and "=" in line:
            if current is not None:
                out.append("\n".join(current))
            current = [line]
        elif current is not None and depth >= 1:
            current.append(line)
        depth += opened - closed
        if depth <= 0 and current is not None:
            out.append("\n".join(current))
            current = None
            depth = 0
            if out:
                break
    return out


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
    ap.add_argument("title", nargs="+", help="one or more article titles")
    ap.add_argument("--rows", type=int, default=30)
    ap.add_argument("--table", type=int, default=0, help="1-based; 0 means every table")
    ap.add_argument("--width", type=int, default=32, help="characters per cell")
    ap.add_argument("--lang", default="en", help="Wikipedia language edition, e.g. ro, bg, sr")
    ap.add_argument("--infobox", action="store_true",
                    help="print the first infobox's parameters instead of the tables")
    args = ap.parse_args()

    for title in args.title:
        show(title, args)
    return 0


def show(title: str, args: argparse.Namespace) -> None:
    q = urllib.parse.urlencode({"action": "parse", "page": title, "prop": "wikitext",
                                "format": "json", "formatversion": "2", "redirects": "1"})
    data = http_json(f"{API.format(lang=args.lang)}?{q}", timeout=90)
    parsed = data.get("parse") or {}
    wikitext = parsed.get("wikitext") or ""
    log(f"\n===== page: {parsed.get('title')!r}, {len(wikitext):,} bytes of wikitext")
    if not wikitext:
        log(f"  {data.get('error') or 'no wikitext'}")
        return
    if args.infobox:
        for entry in infobox_lines(wikitext):
            head, _, rest = entry.partition("=")
            log(f"  {head.strip(' |')} = {' '.join(rest.split())[:args.width]}")
        return
    found = tables(wikitext)
    log(f"  {len(found)} table(s)")
    for i, t in enumerate(found, 1):
        if args.table and i != args.table:
            continue
        log(f"--- table {i}: {len(t)} rows ---")
        for row in t[:args.rows]:
            log("  " + " | ".join(c[:args.width] for c in row))
        if len(t) > args.rows:
            log(f"  ... {len(t) - args.rows} more rows")


if __name__ == "__main__":
    raise SystemExit(main())
