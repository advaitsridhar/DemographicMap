#!/usr/bin/env python3
"""Read-only probes for the Dutch gemeente readers.

CBS's religion-by-gemeente table counts the gemeenten of 2014 and the map
draws those of 2022. What happened to each gemeente in between is recorded by
CBS itself in StatLine 70739ned, "Gebieden; overzicht vanaf 1830": every
gemeente's begin and end date, and in its explanation (the RegioS
description) every merger and boundary change. These probes print that
record compactly, so the crosswalk can be written against what CBS says and
not against memory. Nothing is written; the output is the log.

Usage:
    python -m scripts.fetch_census.netherlands_probe desc GM0014,GM0140 [--width 3000]
    python -m scripts.fetch_census.netherlands_probe changed 20140101 20221231 [--width 600]
"""

from __future__ import annotations

import argparse
import re
from typing import Any

from ._shared import http_json, log

ODATA = "https://opendata.cbs.nl/ODataApi/odata/70739ned/{path}?$format=json"


def rows(path: str) -> list[dict[str, Any]]:
    """Every row of one 70739ned resource, following CBS's next links."""
    url: str | None = ODATA.format(path=path)
    out: list[dict[str, Any]] = []
    while url:
        payload = http_json(url, timeout=300)
        out += payload.get("value", [])
        url = payload.get("odata.nextLink")
    return out


def gemeenten() -> dict[str, dict[str, Any]]:
    """{GM code: {title, begin, end, province, description}} for every gemeente since 1830."""
    described = {r["Key"].strip(): r for r in rows("RegioS")}
    out: dict[str, dict[str, Any]] = {}
    for r in rows("TypedDataSet"):
        key = str(r.get("RegioS") or "").strip()
        if not key.startswith("GM"):
            continue
        meta = described.get(key, {})
        out[key] = {
            "title": str(meta.get("Title") or "").strip(),
            "begin": str(r.get("BegindatumSorteerveld_6") or "").strip(),
            "end": str(r.get("EinddatumSorteerveld_7") or "").strip(),
            "province": str(r.get("Provincie_4") or "").strip(),
            "description": " ".join(str(meta.get("Description") or "").split()),
        }
    return out


def show(code: str, g: dict[str, Any], width: int) -> None:
    log(f"\n## {code} {g['title']!r}: {g['begin']}-{g['end'] or 'now'}, {g['province']}")
    log("   " + g["description"][:width])


def desc(codes: list[str], width: int) -> None:
    table = gemeenten()
    log(f"70739ned: {len(table)} gemeente codes")
    for code in codes:
        if code in table:
            show(code, table[code], width)
        else:
            log(f"\n## {code}: not in 70739ned")


def changed(start: str, stop: str, width: int) -> None:
    """Codes that began or ended in (start, stop], and continuing codes whose
    explanation names a year in that span, with the sentences that do."""
    table = gemeenten()
    years = range(int(start[:4]), int(stop[:4]) + 1)
    ended = {c: g for c, g in table.items() if g["end"] and start < g["end"] <= stop}
    began = {c: g for c, g in table.items() if start < g["begin"] <= stop}
    log(f"70739ned: {len(table)} gemeente codes; {len(ended)} ended and {len(began)} began "
        f"after {start} up to {stop}")
    alive_start = [c for c, g in table.items()
                   if g["begin"] <= start and (not g["end"] or g["end"] > start)]
    alive_stop = [c for c, g in table.items()
                  if g["begin"] <= stop and (not g["end"] or g["end"] > stop)]
    log(f"   in being on {start}: {len(alive_start)}; on {stop}: {len(alive_stop)}")
    log("\n=== ended")
    for code, g in sorted(ended.items(), key=lambda kv: (kv[1]["end"], kv[0])):
        show(code, g, width)
    log("\n=== began")
    for code, g in sorted(began.items(), key=lambda kv: (kv[1]["begin"], kv[0])):
        show(code, g, width)
    log("\n=== continuing, with a change named in the span")
    pattern = re.compile(r"[^.]*\b(?:%s)\b[^.]*\.?" % "|".join(str(y) for y in years))
    for code in sorted(c for c in alive_start if c in alive_stop):
        g = table[code]
        hits = [m.group(0).strip() for m in pattern.finditer(g["description"])]
        if hits:
            log(f"\n## {code} {g['title']!r}")
            for hit in hits:
                log("   - " + hit[:width])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    one = sub.add_parser("desc")
    one.add_argument("codes")
    one.add_argument("--width", type=int, default=3000)
    two = sub.add_parser("changed")
    two.add_argument("start")
    two.add_argument("stop")
    two.add_argument("--width", type=int, default=600)
    args = ap.parse_args()
    if args.cmd == "desc":
        desc([c.strip() for c in args.codes.split(",") if c.strip()], args.width)
    else:
        changed(args.start, args.stop, args.width)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
