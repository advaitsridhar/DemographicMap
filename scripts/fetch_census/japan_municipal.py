#!/usr/bin/env python3
"""Japan: median age and sex ratio for every municipality, 2020 census, by JIS code.

e-Stat table 0004019308 (令和２年国勢調査, 不詳補完結果: 男女，国籍総数か日本人別
平均年齢及び年齢中位数－全国，都道府県，市区町村) gives the median age of every
municipality and ward, with ages the census could not establish imputed by
the Statistics Bureau -- the figures the Bureau itself quotes. Its companion
0004019309 (男女，年齢（5歳階級），国籍総数か日本人別人口) gives the same areas'
men and women, all ages and nationalities, from which the sex ratio is taken. Its areas are
JIS municipal codes with Japanese names; the map's polygons have romanised
names, and 24 of them none. So each value is bound to its polygon by code,
through ``data/processed/code_shapes.json``, which scripts/wikidata_points.py
writes only where a Wikidata item's coordinate and name both say which
polygon that code is. A code with no such binding is left out.

The tables are read against themselves before anything is written: the
national median must lie within the range of the 47 prefectures' medians, as
a median of the whole must, and the nation's men and women must be the sum of
the 47 prefectures'.

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
NATIONAL = "00000"
SOURCE = "Statistics Bureau of Japan, 2020 Census (e-Stat 0004019308, imputed)"
URL = f"https://www.e-stat.go.jp/dbview?sid={TABLE}"
SEX_TABLE = "0004019309"
SEX_SOURCE = "Statistics Bureau of Japan, 2020 Census (e-Stat 0004019309, imputed)"
SEX_URL = f"https://www.e-stat.go.jp/dbview?sid={SEX_TABLE}"


def sexes(key: str) -> dict[str, dict[str, int]]:
    """{area code: {"1": men, "2": women}}, all ages and nationalities."""
    values = fetch_values(key, SEX_TABLE, {"cdTab": "2020_01", "cdCat01": "00", "cdCat02": "0",
                                           "cdCat03": "1,2", "cdTime": "2020000000"})
    out: dict[str, dict[str, int]] = {}
    for v in values:
        try:
            out.setdefault(str(v.get("@area")), {})[str(v.get("@cat03"))] = int(str(v.get("$")))
        except ValueError:
            continue
    national = out.get(NATIONAL, {})
    summed = {s: sum(v.get(s, 0) for c, v in out.items() if c.endswith("000") and c != NATIONAL)
              for s in ("1", "2")}
    if not national or summed != {s: national.get(s) for s in ("1", "2")}:
        raise SystemExit(f"japan_municipal: the prefectures hold {summed}, the nation {national}")
    log(f"  {len(out)} areas with men and women; Japan {national['1']:,} men, "
        f"{national['2']:,} women")
    return out


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
    prefectures = [v for code, v in median.items() if code.endswith("000") and code != NATIONAL]
    national = median.get(NATIONAL)
    if len(prefectures) != 47 or national is None \
            or not min(prefectures) <= national <= max(prefectures):
        raise SystemExit(f"japan_municipal: national median {national} against "
                         f"{len(prefectures)} prefectures "
                         f"({min(prefectures, default=None)}-{max(prefectures, default=None)}); "
                         f"not a table of medians by area")
    log(f"  national median {national:.1f}, prefectures {min(prefectures):.1f}-{max(prefectures):.1f}")
    by_sex = sexes(key)
    shapes = (read_json(PROCESSED / "code_shapes.json", {}) or {}).get("JPN", {})
    records: list[dict[str, Any]] = []
    for code, entry in sorted(shapes.items()):
        men, women = (by_sex.get(code) or {}).get("1"), (by_sex.get(code) or {}).get("2")
        if code not in median and not (men and women):
            continue
        records.append(record(
            f"JPN-{code}", entry["name"], level=entry["level"], parent="JPN",
            country="JPN", codes={"jis": code},
            match_by="shape_id", shape_id=entry["shape_id"],
            median_age=(measure(median[code], unit="years", year=YEAR, source=SOURCE)
                        if code in median else None),
            sex_ratio=(measure(round(1000 * men / women), unit="males_per_1000_females",
                               year=YEAR, source=SEX_SOURCE) if men and women else None),
            sources=[{"field": "median age", "name": SOURCE, "url": URL,
                      "license": ESTAT_LICENCE},
                     {"field": "sex ratio", "name": SEX_SOURCE, "url": SEX_URL,
                      "license": ESTAT_LICENCE}],
        ))
    log(f"  {len(median)} areas in the table; {len(records)} bound to the map's polygons "
        f"by code ({len(shapes)} codes bound)")
    write_json(PROCESSED / "japan_municipal.json", records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
