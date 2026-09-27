#!/usr/bin/env python3
"""What a REDATAM base's dictionary names: its entities, variables and labels.

A REDATAM WebServer portal offers its base's dictionary for download
(``RpWebUtilities.exe/Down_Dictionary.dic?LFN=...``). The file is Redatam+SP's
own binary format, but every name in it -- the entities (PROVINCI, PERSONA),
each variable's name and label, and each category's label -- is stored as
readable text. A reader has to name a variable exactly as the dictionary does
(``PERSONA.P05``), and the portal's own pages print only the labels, so this
prints the dictionary's strings in file order, where a variable's name sits
beside its label and its categories.

Nothing is written; the output is the log.

Usage:
    python -m scripts.probe_redatam_dic "https://host/bin/RpWebUtilities.exe/Down_Dictionary.dic?LFN=RpBases\\X\\X.dic"
    python -m scripts.probe_redatam_dic URL --grep RELIG,ETNI,LENGUA --context 30
"""

from __future__ import annotations

import argparse
import re
import urllib.request

from scripts.probe_redatam import HEADERS

RUN = re.compile(rb"[\x20-\x7e\xa0-\xff]{3,}")


def strings(blob: bytes) -> list[tuple[int, str]]:
    """(offset, text) for each run of three or more printable Latin-1 bytes."""
    return [(m.start(), m.group(0).decode("latin-1").strip()) for m in RUN.finditer(blob)
            if m.group(0).strip()]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("url", nargs="+")
    ap.add_argument("--grep", default="",
                    help="comma-separated words: print only the strings around a match")
    ap.add_argument("--context", type=int, default=20,
                    help="strings printed after each match (and a quarter as many before)")
    ap.add_argument("--max", type=int, default=6000, help="most strings printed per file")
    args = ap.parse_args()
    for url in args.url:
        print(f"dictionary: {url}")
        req = urllib.request.Request(url.replace("\\", "%5C"), headers=HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                blob = resp.read()
                print(f"  {resp.status} {resp.headers.get('Content-Type')} {len(blob):,} bytes")
        except Exception as exc:                      # noqa: BLE001 -- the log is the product
            print(f"  unreadable: {type(exc).__name__}: {str(exc)[:300]}")
            continue
        found = strings(blob)
        print(f"  {len(found):,} strings")
        words = [w.strip().lower() for w in args.grep.split(",") if w.strip()]
        if not words:
            for offset, text in found[:args.max]:
                print(f"  {offset:>8} {text}")
            continue
        shown: set[int] = set()
        printed = 0
        for index, (_, text) in enumerate(found):
            if not any(w in text.lower() for w in words):
                continue
            lo, hi = max(0, index - args.context // 4), min(len(found), index + args.context + 1)
            if printed:
                print("  --")
            for j in range(lo, hi):
                if j in shown:
                    continue
                shown.add(j)
                printed += 1
                print(f"  {found[j][0]:>8} {found[j][1]}")
            if printed >= args.max:
                break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
