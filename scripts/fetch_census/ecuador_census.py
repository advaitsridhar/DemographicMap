"""Ecuador's cantons: the 2022 census count, from INEC's own workbook.

INEC publishes the 2022 census's population by province and canton in
"01_2022_CPV_Estructura_poblacional.xlsx" (sheet 5.1, "Tasa de crecimiento
promedio anual 2010-2022": every canton's 2010 and 2022 count). Its host,
censoecuador.gob.ec, answers an automated reader with 403 however it announces
itself, and this map does not get round a refusal; the Internet Archive holds
a capture of the same file (13 July 2024, served 200 as a workbook), and that
capture is read, cited with the original's address beside it.

Wikidata carries the 2022 figure for 188 of the map's 223 cantons; this is the
census itself for all of them, and fills the 35 that had none -- nineteen of
which had only the figure of the canton's town, which the build refuses.

Two checks: the cantons of every province add up to the province's row, and
the provinces to INEC's national 16,938,986. Nothing is written otherwise.

``--dump`` also saves the sheet as tab-separated text in data/raw/ecuador.

Usage:
    python -m scripts.fetch_census.ecuador_census [--dump] [--offline]
"""
from __future__ import annotations

import argparse
import io
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any

from ._shared import PROCESSED, log, record, write_json

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import measure, slugify  # noqa: E402
from probe_pdf import fetch_blob  # noqa: E402

ORIGINAL = ("https://www.censoecuador.gob.ec/wp-content/uploads/2024/04/"
            "01_2022_CPV_Estructura_poblacional.xlsx")
CAPTURE = f"https://web.archive.org/web/20240713113331id_/{ORIGINAL}"
SHEET = "5.1"
ROOT = Path(__file__).resolve().parent.parent.parent
DUMP = ROOT / "data" / "raw" / "ecuador" / "census2022_sheet5_1.tsv"
OUT = PROCESSED / "ecuador_census.json"
YEAR = 2022
NATIONAL = 16_938_986
SOURCE = ("INEC, Censo de Población y Vivienda 2022, Estructura poblacional, "
          "tabla 5.1")


def fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text or ""))
    return " ".join("".join(c for c in text if not unicodedata.combining(c)).split()).casefold()


def sheet_rows(blob: bytes) -> list[list[str]]:
    import openpyxl
    book = openpyxl.load_workbook(io.BytesIO(blob), read_only=True, data_only=True)
    sheet = book[SHEET]
    return [["" if c is None else str(c) for c in row] for row in sheet.iter_rows(values_only=True)]


def number(cell: str) -> int | None:
    try:
        value = float(cell)
    except (TypeError, ValueError):
        return None
    return int(round(value)) if value > 0 else None


def parse(rows: list[list[str]]) -> tuple[dict[str, int], dict[str, dict[str, int]], int]:
    """(provinces, cantons by province, national) from the sheet's rows.

    A row is (blank, province, canton, 2010, 2022, rate); a province's own row
    names it in both columns or leaves the canton "Total", as the national
    row does.
    """
    header = next(i for i, r in enumerate(rows) if any("2022" in c for c in r)
                  and any("Provincia" in c for c in r))
    col = next(i for i, c in enumerate(rows[header]) if "2022" in c and "Poblaci" in c)
    provinces: dict[str, int] = {}
    cantons: dict[str, dict[str, int]] = defaultdict(dict)
    national = 0
    for row in rows[header + 1:]:
        cells = [c.strip() for c in row]
        if len(cells) <= col:
            continue
        value = number(cells[col])
        names = [c for c in cells[:col] if c and number(c) is None]
        if value is None or not names:
            continue
        if fold(names[0]) == "total nacional":
            national = value
        elif len(names) == 1 or fold(names[1]) in (fold(names[0]), "total"):
            provinces[names[0]] = value
        else:
            cantons[names[0]][names[1]] = value
    return provinces, cantons, national


def build(rows: list[list[str]]) -> list[dict[str, Any]]:
    provinces, cantons, national = parse(rows)
    bad = {p: (v, sum(cantons[p].values())) for p, v in provinces.items()
           if sum(cantons[p].values()) != v}
    total = sum(provinces.values())
    log(f"  {len(provinces)} provinces, {sum(len(c) for c in cantons.values())} cantons; "
        f"provinces sum to {total:,}, national row {national:,}")
    if national != NATIONAL or total != NATIONAL or bad or not provinces:
        raise SystemExit(f"the sheet does not add up (provinces off: {bad}); nothing written")
    cite = [{"field": "population", "name": SOURCE, "url": ORIGINAL,
             "archived": CAPTURE}]
    out = []
    for province, value in sorted(provinces.items()):
        name = province.title() if province.isupper() else province
        out.append(record(f"ECU-CEN-{slugify(name)}", name, level="admin1", parent="ECU",
                          country="ECU", population=measure(value, year=YEAR, source=SOURCE),
                          sources=cite))
        for canton, people in sorted(cantons[province].items()):
            label = canton.title() if canton.isupper() else canton
            out.append(record(f"ECU-CEN-{slugify(name)}-{slugify(label)}", label,
                              level="admin2", parent="ECU", country="ECU", parent_name=name,
                              aliases=[f"Cantón {label}"],
                              population=measure(people, year=YEAR, source=SOURCE),
                              sources=cite))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dump", action="store_true", help="also save the sheet as text")
    ap.add_argument("--offline", action="store_true", help="read the saved text")
    args = ap.parse_args()
    if args.offline:
        rows = [line.split("\t") for line in DUMP.read_text(encoding="utf-8").split("\n")]
    else:
        blob = fetch_blob(CAPTURE)
        log(f"  {CAPTURE}: {len(blob):,} bytes")
        rows = sheet_rows(blob)
        if args.dump:
            DUMP.parent.mkdir(parents=True, exist_ok=True)
            DUMP.write_text("\n".join("\t".join(r) for r in rows), encoding="utf-8")
            log(f"  wrote {DUMP.relative_to(ROOT)} ({len(rows)} rows)")
    write_json(OUT, build(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
