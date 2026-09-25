#!/usr/bin/env python3
"""Japan: median age for every municipality, 2020 census, bound by JIS code.

e-Stat table 0004019308 (令和２年国勢調査, 不詳補完結果: 男女，国籍総数か日本人別
平均年齢及び年齢中位数－全国，都道府県，市区町村) gives the median age of every
municipality and ward, with ages the census could not establish imputed by
the Statistics Bureau -- the figures the Bureau itself quotes. Its areas are
JIS municipal codes with Japanese names; the map's polygons have romanised
names, and 24 of them none. So each value is bound to its polygon by code,
through ``data/processed/code_shapes.json``, which scripts/wikidata_points.py
writes only where a Wikidata item's coordinate and name both say which
polygon that code is. A code with no such binding is left out.

The table is read against itself before anything is written: the national
median must be the published 48.6 years (結果の概要).

Usage:
    python -m scripts.fetch_census.japan_municipal     # needs ESTAT_API
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import PROCESSED, log, measure, read_json, write_json  # noqa: E402
from probe_estat import app_id  # noqa: E402

from fetch_census._shared import record  # noqa: E402
from fetch_census.japan import ESTAT_LICENCE, fetch_values  # noqa: E402

TABLE = "0004019308"
MEDIAN = "2020i_40"
YEAR = 2020
NATIONAL, PUBLISHED = "00000", 48.6
SOURCE = "Statistics Bureau of Japan, 2020 Census (e-Stat 0004019308, imputed)"
URL = f"https://www.e-stat.go.jp/dbview?sid={TABLE}"


def main() -> int:
    key = app_id()
    values = fetch_values(key, TABLE, {"cdTab": MEDIAN, "cdCat01": "0", "cdCat02": "0",
                                       "cdTime": "2020000000"})
    median: dict[str, float] = {}
    for v in values:
        try:
            median[str(v.get("@area"))] = float(v.get("$"))
        except (TypeError, ValueError):
            continue
    if abs(median.get(NATIONAL, 0) - PUBLISHED) > 0.05:
        raise SystemExit(f"japan_municipal: national median {median.get(NATIONAL)} is not "
                         f"the published {PUBLISHED}; not the table this was written for")
    shapes = (read_json(PROCESSED / "code_shapes.json", {}) or {}).get("JPN", {})
    records: list[dict[str, Any]] = []
    for code, entry in sorted(shapes.items()):
        if code not in median:
            continue
        records.append(record(
            f"JPN-{code}", entry["name"], level=entry["level"], parent="JPN",
            country="JPN", codes={"jis": code},
            match_by="shape_id", shape_id=entry["shape_id"],
            median_age=measure(median[code], unit="years", year=YEAR, source=SOURCE),
            sources=[{"field": "median age", "name": SOURCE, "url": URL,
                      "license": ESTAT_LICENCE}],
        ))
    log(f"  {len(median)} areas in the table; {len(records)} bound to the map's polygons "
        f"by code ({len(shapes)} codes bound)")
    write_json(PROCESSED / "japan_municipal.json", records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
