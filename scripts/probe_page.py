#!/usr/bin/env python3
"""Report what a web page says around the words you are after.

``probe_links.py`` reads a page's links, which answers "where does this
catalogue go" and nothing about the page's own text. This answers the other
question: a source has been named -- an article, a report page, a Wikipedia
section -- and before deciding whether it is worth an adapter, what does it
actually say about the thing being looked for, and where do its numbers come
from?

Nothing is written and nothing is committed; the output is the log. Tags are
stripped, tables are flattened one cell per line so a figure keeps the row
label beside it, and only the matching lines are printed with their context.

Wikipedia is fetched through the MediaWiki API rather than by scraping, the
same way ``wiki_census.py`` does, so a section can be asked for by name and
comes back as its own text rather than as a whole article to search.

Usage:
    python -m scripts.probe_page https://example.org/article --terms Shia,Sunni
    python -m scripts.probe_page https://en.wikipedia.org/wiki/Gilgit-Baltistan \
        --section Demographics --terms language,religion
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import http_get, log  # noqa: E402

WIKI_API = "https://en.wikipedia.org/w/api.php"

# Block-level tags whose close is a line break in the text, so a table cell or
# a list item does not run into the next one and lose which row it was on.
BLOCKS = ("</p>", "</div>", "</td>", "</th>", "</tr>", "</li>", "</h1>",
          "</h2>", "</h3>", "</h4>", "<br>", "<br/>", "<br />", "</caption>")


def readable(markup: str) -> list[str]:
    """Tags out, one line per block, blank lines dropped."""
    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", markup)
    for tag in BLOCKS:
        text = text.replace(tag, tag + "\n")
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = html.unescape(text)
    out = []
    for line in text.splitlines():
        line = re.sub(r"[ \t\xa0]+", " ", line).strip()
        if line:
            out.append(line)
    return out


def wiki_section(title: str, section: str | None) -> list[str]:
    """One Wikipedia section as text, or the whole article when none is named.

    Asked of the API rather than scraped: the section index has to be looked
    up first, because a section's number depends on how many came before it
    and hard-coding one would silently read a different section the next time
    somebody adds a paragraph.
    """
    base = (f"{WIKI_API}?action=parse&page={urllib.parse.quote(title)}"
            f"&format=json&formatversion=2")
    if section:
        listing = json.loads(http_get(f"{base}&prop=sections"))
        wanted = [s for s in listing["parse"]["sections"]
                  if s["line"].casefold() == section.casefold()]
        if not wanted:
            names = ", ".join(s["line"] for s in listing["parse"]["sections"])
            raise SystemExit(f"probe_page: {title} has no section named "
                             f"{section!r}. It has: {names}")
        base += f"&section={wanted[0]['index']}"
    page = json.loads(http_get(f"{base}&prop=text"))
    return readable(page["parse"]["text"])


def report(lines: list[str], terms: list[str], context: int) -> None:
    hits = [i for i, line in enumerate(lines)
            if any(t.casefold() in line.casefold() for t in terms)]
    log(f"  {len(lines)} lines of text, {len(hits)} mentioning "
        f"{', '.join(terms)}")
    shown: set[int] = set()
    for i in hits:
        for j in range(max(0, i - context), min(len(lines), i + context + 1)):
            if j not in shown:
                shown.add(j)
                log(f"    {j:>5}  {lines[j][:300]}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("url", help="page to read, or a Wikipedia article URL")
    ap.add_argument("--section", help="Wikipedia section to read on its own")
    ap.add_argument("--terms", default="religion,language,population",
                    help="comma-separated words to report around")
    ap.add_argument("--context", type=int, default=2)
    args = ap.parse_args()

    terms = [t.strip() for t in args.terms.split(",") if t.strip()]
    match = re.match(r"https?://en\.wikipedia\.org/wiki/([^#?]+)", args.url)
    if match:
        title = urllib.parse.unquote(match.group(1))
        log(f"probe_page: en.wikipedia.org {title}"
            + (f" § {args.section}" if args.section else ""))
        lines = wiki_section(title, args.section)
    else:
        log(f"probe_page: {args.url}")
        body = http_get(args.url)
        lines = readable(body.decode("utf-8", "replace")
                         if isinstance(body, bytes) else body)
    report(lines, terms, args.context)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
