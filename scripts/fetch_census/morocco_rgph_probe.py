#!/usr/bin/env python3
"""What the RGPH 2024 results portal's saved charts hold: a reader's look.

The Haut-Commissariat au Plan publishes the 2024 census results on a public
dashboard (``resultats2024.rgphapps.ma``) whose saved charts answer
``/api/v1/chart/<id>/data/``. This prints, for each chart asked for, its SQL,
its row count, the indicators it carries with how many rows each, and a few
rows per zone level -- to see which figures by region and province are there.

Usage:
    python -m scripts.fetch_census.morocco_rgph_probe --chart 669 --chart 807
    python -m scripts.fetch_census.morocco_rgph_probe --chart 807 --grep mahbass
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict

from ._shared import http_get, log

BASE = "https://resultats2024.rgphapps.ma/api/v1/chart/{}/data/?format=json"


def show(chart: int, rows_per: int, grep: str = "") -> None:
    body = json.loads(http_get(BASE.format(chart), cache=False, timeout=180))
    for result in body.get("result", []):
        data = result.get("data") or []
        log(f"== chart {chart}: {result.get('rowcount')} rows; columns {result.get('colnames')}")
        log("  query: " + " ".join(str(result.get("query", "")).split())[:900])
        cols = result.get("colnames") or []
        ind = next((c for c in cols if "indicateur" in c.lower() and "titre" in c.lower()), None)
        val = next((c for c in cols if "valeur" in c.lower()), None)
        zone = next((c for c in cols if c.lower() == "zone"), None)
        if grep:
            # Every row whose zone (or any cell) matches: a commune's rows,
            # wherever the chart's row limit left them.
            hits = [r for r in data if re.search(grep, json.dumps(r, ensure_ascii=False), re.I)]
            log(f"  {len(hits)} rows match {grep!r}:")
            for r in hits[:400]:
                log(f"    {json.dumps(r, ensure_ascii=False)[:400]}")
        if ind:
            counts = Counter(r.get(ind) for r in data)
            log(f"  {len(counts)} indicators:")
            for name, n in counts.most_common():
                vals = [r.get(val) for r in data if r.get(ind) == name and r.get(val) is not None]
                log(f"    {n:6d}  {name!r}  values {min(vals) if vals else None}..{max(vals) if vals else None}")
        if zone:
            levels = defaultdict(list)
            for r in data:
                levels[str(r.get(zone)).count(" -> ")].append(r)
            for depth, rows in sorted(levels.items()):
                zones = {r.get(zone) for r in rows}
                log(f"  depth {depth}: {len(rows)} rows, {len(zones)} zones")
                for r in rows[:rows_per]:
                    log(f"    {json.dumps(r, ensure_ascii=False)[:300]}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--chart", type=int, action="append", required=True)
    ap.add_argument("--rows", type=int, default=6)
    ap.add_argument("--grep", default="", help="print every row matching this regex")
    args = ap.parse_args()
    for chart in args.chart:
        try:
            show(chart, args.rows, args.grep)
        except Exception as exc:                    # noqa: BLE001 -- a probe reports and goes on
            log(f"== chart {chart}: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
