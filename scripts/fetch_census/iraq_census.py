"""Iraq's districts: the 2024 census, from the Annual Abstract of Statistics.

Iraq counted its people in November 2024, the first census since 1997, and
COSIT prints the result in Part Two of its Annual Abstract of Statistics 2024:
Table 11/2 gives every sub-district (nahiya) its population, by sex and by
urban and rural, under its district (qadhaa) and governorate, each with its
COSIT code. OCHA's population tables for Iraq stop at the governorate, and
Wikidata has no figure for most districts, so 86 of the map's 101 were blank.

``--dump`` writes the table's pages as laid-out text to data/raw/iraq, which
is what the parser is written against.

Usage:
    python -m scripts.fetch_census.iraq_census --dump
    python -m scripts.fetch_census.iraq_census
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ._shared import log

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from probe_pdf import PAGE_BREAK, fetch_blob, laid_out  # noqa: E402

URL = "https://cosit.gov.iq/documents/AAS2024/02.pdf"
# OCHA's gazetteer of the boundaries the map draws (cod-ab-irq, CC BY-IGO):
# which sub-district lies in which of the 101 districts.
GAZETTEER = ("https://data.humdata.org/dataset/488bb3cd-3ce9-49d3-862a-3ce7975c63e1/"
             "resource/bde103b3-dc51-4e7b-9fd2-e38fa5600dc6/download/irq_admin_boundaries.xlsx")
ROOT = Path(__file__).resolve().parent.parent.parent
DUMP = ROOT / "data" / "raw" / "iraq" / "aas2024_table11.txt"
GAZ_DUMP = ROOT / "data" / "raw" / "iraq" / "ocha_admin3.txt"


def gazetteer_rows(blob: bytes) -> list[list[str]]:
    """Every sheet's rows that name a sub-district, as tab-separated text."""
    import io

    import openpyxl
    book = openpyxl.load_workbook(io.BytesIO(blob), read_only=True, data_only=True)
    out: list[list[str]] = []
    for sheet in book.worksheets:
        rows = list(sheet.iter_rows(values_only=True))
        if not rows:
            continue
        header = [str(c or "") for c in rows[0]]
        log(f"  sheet {sheet.title!r}: {len(rows) - 1} rows, {header[:14]}")
        if not any(h.upper().startswith("ADM3") for h in header):
            continue
        out.append(header)
        out.extend([["" if c is None else str(c) for c in row] for row in rows[1:]])
    return out


def table_pages(text: str) -> list[str]:
    """The pages of Table 11/2: those whose header names a nahiya."""
    return [page for page in text.split(PAGE_BREAK) if "Nahiya" in page]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dump", action="store_true")
    args = ap.parse_args()
    blob = fetch_blob(URL)
    log(f"  {URL}: {len(blob):,} bytes")
    pages = table_pages(laid_out(blob))
    log(f"  {len(pages)} pages of Table 11/2")
    if args.dump:
        DUMP.parent.mkdir(parents=True, exist_ok=True)
        DUMP.write_text(PAGE_BREAK.join(pages), encoding="utf-8")
        log(f"  wrote {DUMP.relative_to(ROOT)}")
        rows = gazetteer_rows(fetch_blob(GAZETTEER))
        GAZ_DUMP.write_text("\n".join("\t".join(r) for r in rows), encoding="utf-8")
        log(f"  wrote {GAZ_DUMP.relative_to(ROOT)} ({len(rows)} rows)")
        return 0
    raise SystemExit("the parser is not written yet; run with --dump")


if __name__ == "__main__":
    raise SystemExit(main())
