#!/usr/bin/env python3
"""Europe: religion, language and ethnicity from each unit's own Wikipedia
article, at first and second level.

This is the Indonesian method (``indonesia.py``) turned on Europe, by the
owner's decision of 20 September 2026: read what a place's article publishes
about who lives there, take it only where the article cites something and the
citation can be dated, and leave a stated reason where it cannot.

Europe differs from Indonesia in three ways this module has to handle rather
than paper over:

* **A different edition per country.** The Romanian article of a commune
  carries its 2021 census ethnicity and religion tables; the English one
  carries a sentence. The spec names the edition, and the source line names
  it too, because which edition a figure was read from is part of where it
  came from.
* **A different template per country.** There is no European infobox. Some
  countries put the composition in a table under a "Demographics" heading,
  some in the infobox, and most nowhere at all.
* **A list is not a composition.** Many articles name the languages spoken in
  a place without a share for any of them. That is a list, and this module
  never turns one into a composition.

Usage:
    python -m scripts.fetch_census.europe_wiki --probe ro:Adamclisi,_Constanța
    python -m scripts.fetch_census.europe_wiki --country BGR
    python -m scripts.fetch_census.europe_wiki
"""

from __future__ import annotations

import argparse
import re
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Any

from ._shared import PROCESSED, http_json, log, write_json

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from probe_wikitable import infobox_lines, plain, tables  # noqa: E402

PAUSE = 0.3
BACKOFF = (60, 120, 240)


def api(lang: str) -> str:
    return f"https://{lang}.wikipedia.org/w/api.php"


def fetch(title: str, lang: str) -> tuple[str, str]:
    """The article's wikitext and the title it resolved to."""
    q = urllib.parse.urlencode({"action": "parse", "page": title, "prop": "wikitext",
                                "format": "json", "formatversion": "2", "redirects": "1"})
    time.sleep(PAUSE)
    for wait in (*BACKOFF, None):
        try:
            data = http_json(f"{api(lang)}?{q}", timeout=90)
            break
        except RuntimeError as exc:
            if wait is None:
                raise
            log(f"  [{lang}] {title!r}: {exc}; waiting {wait}s")
            time.sleep(wait)
    parsed = data.get("parse") or {}
    text = parsed.get("wikitext") or ""
    if not text:
        log(f"  [{lang}] {title!r}: nothing ({(data.get('error') or {}).get('code')})")
    return text, parsed.get("title") or title


# ---------------------------------------------------------------------------
# Probe
# ---------------------------------------------------------------------------

COMPOSITION = re.compile(
    r"etni|naţional|nacional|национал|етни|этни|религ|confes|конфес|рели|"
    r"veroispoved|vallás|nemzetiség|národnost|náboženstv|jezik|język|"
    r"limba|език|мова|мова|language|religio|ethnic|nationalit|faith|"
    r"maternal|matern|anyanyelv|kalba|valoda|keel|usk|rahvus|tautyb|tautīb",
    re.I)


def probe(spec: str, rows: int, width: int) -> None:
    """Print one article's infobox parameters and its composition-looking tables.

    ``spec`` is "lang:Title"; a title carries underscores rather than spaces,
    because the runner hands this command to xargs and xargs splits on
    whitespace.
    """
    lang, _, title = spec.partition(":")
    wikitext, resolved = fetch(title.replace("_", " "), lang)
    log(f"\n===== [{lang}] {resolved!r}, {len(wikitext):,} bytes")
    if not wikitext:
        return
    log("  -- infobox --")
    for entry in infobox_lines(wikitext):
        head, _, rest = entry.partition("=")
        log(f"    {head.strip(' |')} = {' '.join(rest.split())[:width]}")
    found = tables(wikitext)
    log(f"  -- {len(found)} table(s) --")
    for i, table in enumerate(found, 1):
        flat = " ".join(" ".join(r) for r in table[:3])
        if not COMPOSITION.search(flat):
            log(f"    table {i}: {len(table)} rows, not a composition: {flat[:80]}")
            continue
        log(f"    table {i}: {len(table)} rows")
        for row in table[:rows]:
            log("      " + " | ".join(c[:width] for c in row))
        if len(table) > rows:
            log(f"      ... {len(table) - rows} more rows")
    # The sections, so a reader of the log knows what else the article holds.
    heads = re.findall(r"^\s*=+\s*(.+?)\s*=+\s*$", wikitext, re.M)
    log(f"  -- sections: {', '.join(h for h in heads)[:400]}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--probe", nargs="+", metavar="LANG:TITLE",
                    help="print one or more articles' infobox and tables")
    ap.add_argument("--rows", type=int, default=25)
    ap.add_argument("--width", type=int, default=40)
    args = ap.parse_args(argv)
    if args.probe:
        for spec in args.probe:
            probe(spec, args.rows, args.width)
        return 0
    ap.error("nothing to do yet")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
