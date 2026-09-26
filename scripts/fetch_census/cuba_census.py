#!/usr/bin/env python3
"""Cuba: ONEI's municipal dashboard and the 2012 census's skin colour.

Usage:
    python -m scripts.fetch_census.cuba_census --probe
"""

from __future__ import annotations

import argparse
import io
from collections import Counter

from ._shared import http_get, log

WAYBACK = "http://web.archive.org/web/{stamp}id_/{url}"
TABLERO = ("https://www.onei.gob.cu/sites/default/files/publicaciones/2025-05/"
           "3-tablero-municipal.xlsx")
TABLERO_STAMP = "20250606173952"


def probe() -> None:
    import openpyxl
    body = http_get(WAYBACK.format(stamp=TABLERO_STAMP, url=TABLERO), binary=True, cache=False)
    book = openpyxl.load_workbook(io.BytesIO(body), read_only=True, data_only=True)
    rows = [list(r) for r in book["Base"].iter_rows(values_only=True)]
    first = next(i for i, r in enumerate(rows) if any(str(c).strip() == "Año" for c in r))
    rows = rows[first:]
    head = [str(c).strip() for c in rows[0]]
    log(f"  Base: {len(rows)} rows; columns: {head}")
    at = {h: i for i, h in enumerate(head)}
    for column in ("Año", "Territorios", "Edades", "Edad repro-ductiva"):
        values = Counter(str(r[at[column]]) for r in rows[1:])
        log(f"  {column}: {len(values)} values: {sorted(values.items())[:60]}")
    provinces = Counter(str(r[at["Provincias"]]) for r in rows[1:])
    log(f"  Provincias: {sorted(provinces.items())}")
    municipios = {str(r[at["Municipios"]]) for r in rows[1:]}
    log(f"  Municipios: {len(municipios)}: {sorted(municipios)[:200]}")
    for r in rows[1:]:
        if str(r[at["Municipios"]]).startswith("2101") and str(r[at["Año"]]) in ("2023", "2024"):
            log(f"  {r[:12]}")
    for r in rows[1:40]:
        log(f"  {r[:10]}")
    sheet = [list(r) for r in book["Municipios"].iter_rows(values_only=True)]
    for r in sheet[:49]:
        log(f"  Municipios sheet: {r}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--probe", action="store_true")
    args = ap.parse_args()
    if args.probe:
        probe()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
