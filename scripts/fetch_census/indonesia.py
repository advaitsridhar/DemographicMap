#!/usr/bin/env python3
"""Indonesia: ethnicity and religion by province and regency, from the 2010
census as the Indonesian Wikipedia transcribes it.

Probe modes only for now; the reader follows once the tables have been seen.

Usage:
    python -m scripts.fetch_census.indonesia --infobox "Kabupaten Cilacap" "Kota Manado"
"""

from __future__ import annotations

import argparse
import re
import sys
import urllib.parse
from pathlib import Path
from typing import Any

from ._shared import http_json, log

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

API = "https://id.wikipedia.org/w/api.php"
INFOBOX_KEYS = re.compile(r"^\s*\|\s*(agama|suku|suku[_ ]bangsa|bahasa|penduduk|"
                          r"tahun|sumber|populasi|jumlah_penduduk|population|"
                          r"religion|ethnic|kepadatan|data_tahun|tahun_data)"
                          r"[^=]*=", re.I)


def fetch(title: str) -> str:
    q = urllib.parse.urlencode({"action": "parse", "page": title, "prop": "wikitext",
                                "format": "json", "formatversion": "2", "redirects": "1"})
    data = http_json(f"{API}?{q}", timeout=90)
    parsed = data.get("parse") or {}
    text = parsed.get("wikitext") or ""
    log(f"  [id] {title!r} -> {parsed.get('title')!r}: {len(text):,} bytes"
        + ("" if text else f" ({data.get('error')})"))
    return text


def infobox_lines(wikitext: str) -> list[str]:
    """Top-level ``| key = value`` lines of the article's first infobox, whole.

    A value runs until the next top-level parameter, so a multi-line
    ``agama`` list comes back as one entry.
    """
    out: list[str] = []
    depth = 0
    current: list[str] | None = None
    for line in wikitext.split("\n"):
        opened = line.count("{{")
        closed = line.count("}}")
        if depth >= 1 and line.lstrip().startswith("|") and depth == 1 and "=" in line:
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


def probe_infobox(titles: list[str], width: int) -> None:
    for title in titles:
        text = fetch(title)
        for entry in infobox_lines(text):
            if INFOBOX_KEYS.match(entry):
                flat = " ".join(entry.split())
                log(f"     {flat[:width]}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--infobox", nargs="+", default=[], metavar="TITLE",
                    help="print the demographic parameters of these articles' infoboxes")
    ap.add_argument("--width", type=int, default=900)
    args = ap.parse_args()
    if args.infobox:
        probe_infobox(args.infobox, args.width)
        return 0
    ap.error("nothing to do")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
