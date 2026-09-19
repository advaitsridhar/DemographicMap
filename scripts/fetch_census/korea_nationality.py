#!/usr/bin/env python3
"""South Korea: nationality as ethnicity, by province and district, by the owner's decision.

Draft: the ``--inspect`` mode prints what the Ministry of Justice's zipped
CSV release holds, so the reader can be written against what the file says
rather than what its catalogue entry promises.

Usage:
    python -m scripts.fetch_census.korea_nationality --inspect
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
import zipfile
from collections import Counter
from pathlib import Path

from ._shared import http_get, log

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# data.go.kr 15108413, 법무부_시군구별 국적별 등록외국인 체류현황 (2022-2023),
# one zip of two CSVs, one per year, cp949.
MOJ_DATASET = "https://www.data.go.kr/data/15108413/fileData.do"
MOJ_URL = ("https://www.data.go.kr/cmm/cmm/fileDownload.do"
           "?atchFileId=FILE_000000002903067&fileDetailSn=1&insertDataPrcus=N")
ENCODING = "cp949"


def members(blob: bytes) -> dict[str, bytes]:
    """{member name decoded as cp949: bytes} for every CSV in the archive."""
    archive = zipfile.ZipFile(io.BytesIO(blob))
    out: dict[str, bytes] = {}
    for info in archive.infolist():
        # zipfile decodes a non-UTF-8 name as cp437; the bytes are cp949.
        raw = info.filename.encode("cp437", "replace") if not info.flag_bits & 0x800 \
            else info.filename.encode("utf-8")
        name = raw.decode(ENCODING, "replace")
        if name.lower().endswith(".csv"):
            out[name] = archive.read(info)
    return out


def rows_of(data: bytes) -> list[list[str]]:
    text = data.decode(ENCODING, "replace").lstrip("﻿")
    return [row for row in csv.reader(io.StringIO(text, newline=""))]


def inspect(url: str, rows: int, width: int) -> None:
    blob = http_get(url, binary=True, cache=False)
    assert isinstance(blob, bytes)
    log(f"inspect: {url} ({len(blob):,} bytes)")
    for name, data in members(blob).items():
        table = rows_of(data)
        log(f"\n=== {name}: {len(table):,} rows, {len(table[0]) if table else 0} columns")
        if not table:
            continue
        header = table[0]
        log(f"  first columns: {header[:width]}")
        log(f"  last columns: {header[-6:]}")
        for row in table[1:rows + 1]:
            log(f"  {row[:width]} ... {row[-3:]}")
        for col in range(min(3, len(header))):
            values = Counter(r[col] for r in table[1:] if len(r) > col)
            log(f"  column {col} {header[col]!r}: {len(values)} distinct; "
                f"{list(values.items())[:70]}")
        # The districts of one province, to see whether the file lists
        # a city with districts as one row or as its districts.
        for sido in ("경기도", "경기"):
            listed = [r[1] for r in table[1:] if len(r) > 2 and r[0] == sido]
            if listed:
                log(f"  {sido}: {sorted(set(listed))}")
                break


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--inspect", nargs="?", const=MOJ_URL, default=None, metavar="URL",
                    help="print the shape of the zipped CSV release and stop")
    ap.add_argument("--rows", type=int, default=8)
    ap.add_argument("--width", type=int, default=8)
    args = ap.parse_args()
    if args.inspect:
        inspect(args.inspect, args.rows, args.width)
        return 0
    raise SystemExit("korea_nationality: the reader is not written yet; use --inspect")


if __name__ == "__main__":
    sys.exit(main())
