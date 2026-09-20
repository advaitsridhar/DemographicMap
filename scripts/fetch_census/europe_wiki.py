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

PROBE_LOG = PROCESSED / "europe_wiki_probe.log"
_probe_lines: list[str] = []


def say(line: str) -> None:
    """Print, and keep it for the probe's own log file.

    The runner tees every run into data/processed/last-run.log and commits
    it, so two adapters dispatched minutes apart overwrite each other's
    answer -- the first Europe probe's log was gone by the time it was read,
    replaced by an unrelated catalogue listing. A probe's whole product is
    what it printed, so it also writes a file of its own that nothing else
    touches.
    """
    log(line)
    _probe_lines.append(line)


COMPOSITION = re.compile(
    r"etni|na[tţț]ional|nacional|национал|етни|этни|религ|confes|конфес|рели|"
    r"veroispoved|vallás|nemzetiség|národnost|náboženstv|jezik|język|"
    r"limba|език|мова|language|religio|ethnic|nationalit|faith|мов|"
    r"anyanyelv|kalba|valoda|keel|usk|rahvus|tautyb|tautīb|"
    r"demogra|населен|становништв|composition|населення|popula|"
    r"вероисповед|склад|состав|склау|fe[j]?e|besim|gjuh|struktur",
    re.I)

HEADING = re.compile(r"^\s*(=+)\s*(.+?)\s*\1\s*$", re.M)
REF = re.compile(r"<ref\b([^>/]*)(?:/>|>(.*?)</ref>)", re.S | re.I)


def sections(wikitext: str) -> list[tuple[str, str]]:
    """(heading, body) for every section, with the lead under ""."""
    out: list[tuple[str, str]] = []
    last, name = 0, ""
    for m in HEADING.finditer(wikitext):
        out.append((name, wikitext[last:m.start()]))
        name, last = m.group(2), m.end()
    out.append((name, wikitext[last:]))
    return out


def probe(spec: str, rows: int, width: int) -> None:
    """Print one article's infobox parameters and its composition sections.

    A European unit's article almost never names the field in the table's
    own header -- Bulgaria's ethnic table starts "Численост | Дял (в %)" and
    says what it counts in the heading above it -- so the tables are printed
    under the section they sit in, and a section is shown when either its
    heading or its first rows name one of the three fields.

    ``spec`` is "lang:Title"; a title carries underscores rather than spaces,
    because the runner hands this command to xargs and xargs splits on
    whitespace.
    """
    lang, _, title = spec.partition(":")
    wikitext, resolved = fetch(title.replace("_", " "), lang)
    say(f"\n===== [{lang}] {resolved!r}, {len(wikitext):,} bytes")
    if not wikitext:
        return
    say("  -- infobox --")
    for entry in infobox_lines(wikitext):
        head, _, rest = entry.partition("=")
        key = head.strip(" |")
        value = " ".join(rest.split())
        if COMPOSITION.search(key) or COMPOSITION.search(value[:60]):
            say(f"    * {key} = {value[:4 * width]}")
        else:
            say(f"      {key} = {value[:width]}")
    say("  -- sections --")
    for name, body in sections(wikitext):
        found = tables(body)
        flat = " ".join(" ".join(r) for t in found for r in t[:3])
        interesting = COMPOSITION.search(name) or COMPOSITION.search(flat[:400])
        if not found:
            say(f"    [{name}] no table")
            continue
        if not interesting:
            say(f"    [{name}] {len(found)} table(s), not a composition: {flat[:70]}")
            continue
        say(f"    [{name}] {len(found)} table(s)")
        for m in REF.finditer(body):
            attrs, cite = m.group(1), m.group(2)
            say(f"      ref{attrs.strip() and ' ' + attrs.strip() or ''}: "
                f"{' '.join((cite or '').split())[:3 * width]}")
        for i, table in enumerate(found, 1):
            say(f"      table {i}: {len(table)} rows")
            for row in table[:rows]:
                say("        " + " | ".join(c[:width] for c in row))
            if len(table) > rows:
                say(f"        ... {len(table) - rows} more rows")


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
        PROBE_LOG.parent.mkdir(parents=True, exist_ok=True)
        PROBE_LOG.write_text("\n".join(_probe_lines) + "\n", encoding="utf-8")
        log(f"\nwrote {PROBE_LOG}")
        return 0
    ap.error("nothing to do yet")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
