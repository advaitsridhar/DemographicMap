#!/usr/bin/env python3
"""Zimbabwe: religion and mother tongue by province, 2022 Population and Housing Census.

ZIMSTAT's 2022 PHC Report prints religion by province for both sexes as
Table 2.14(c) (eleven classes and a total) and mother tongue as Table 2.17
(seventeen languages down the side, the ten provinces across). Every figure
is printed with comma thousands, so a row reads unambiguously as text. The
ten provinces carried Afrobarometer survey shares for religion; the census
replaces them, and ethnicity, which the report publishes for the country
only (Table 2.15), keeps the survey figures.

Checks: each religion row's classes sum to its printed total, each language
row's provinces sum to its printed total, and each province's languages sum
to the printed province total.

Usage:
    python -m scripts.fetch_census.zimbabwe
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

from ._shared import PROCESSED, log, record, shares, write_json

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from probe_pdf import PAGE_BREAK, fetch_text  # noqa: E402

OUT = "zimbabwe_province.json"
YEAR = 2022
URL = "https://www.zimstat.co.zw/wp-content/uploads/Census/2022_PHC_Report_27012023_Final.pdf"
SOURCE = "ZIMSTAT, 2022 Population and Housing Census Report (Tables 2.14(c) and 2.17)"
LICENCE = "Official statistics publication of the Zimbabwe National Statistics Agency"

PROVINCES = ["Bulawayo", "Manicaland", "Mashonaland Central", "Mashonaland East",
             "Mashonaland West", "Matabeleland North", "Matabeleland South", "Midlands",
             "Masvingo", "Harare"]
RELIGIONS = ["African traditional religion", "Roman Catholic", "Protestant", "Apostolic sect",
             "Pentecostal", "Other Christian", "Islam", "Judaism", "Hinduism", "No religion",
             "Other religion"]
LANGUAGES = {"Shona": "Shona", "Ndebele": "Ndebele", "English": "English", "Kalanga": "Kalanga",
             "Koisan": "Khoisan", "Nambya": "Nambya", "Ndau": "Ndau", "Chibarwe": "Chibarwe",
             "Shangani": "Shangani", "Chewa": "Chewa", "Sign Language": "Sign language",
             "Sotho": "Sotho", "Tonga": "Tonga", "Tswana": "Tswana", "Venda": "Venda",
             "Xhosa": "Xhosa", "Other": "Other languages"}
NOTES = {
    "religion": "Table 2.14(c): religion of the whole population in the eleven classes the "
                "report prints; the Apostolic sect, Pentecostal and Protestant classes are "
                "the report's own and are kept apart.",
    "language": "Table 2.17: mother tongue as the report groups it. The table covers "
                "13,913,253 people against a census population of 15,178,957, and the "
                "report does not state the table's age floor on the page.",
}
NUMBER = r"(\d{1,3}(?:,\d{3})*|-)"


def number(text: str) -> int:
    return 0 if text == "-" else int(text.replace(",", ""))


def rows(page: str, labels: list[str], width: int) -> dict[str, list[int]]:
    """{label: numbers} for the rows starting with a known label and carrying
    exactly ``width`` figures."""
    out: dict[str, list[int]] = {}
    pattern = re.compile(r"^(" + "|".join(re.escape(l) for l in sorted(labels, key=len, reverse=True))
                         + r")\s+((?:" + NUMBER + r"\s*){" + str(width) + r"})\s*$")
    for line in page.splitlines():
        m = pattern.match(line.strip())
        if m:
            out[m.group(1)] = [number(t) for t in m.group(2).split()]
    return out


def table_page(text: str, heading: str, labels: list[str], width: int) -> dict[str, list[int]]:
    for page in text.split(PAGE_BREAK):
        if heading in page:
            got = rows(page, labels, width)
            if len(got) == len(labels):
                return got
    raise SystemExit(f"zimbabwe: no page carries {heading!r} with all {len(labels)} rows of "
                     f"{width} figures")


def read_religion(text: str) -> dict[str, dict[str, int]]:
    table = table_page(text, "Table 2.14(c)", PROVINCES + ["Total"], len(RELIGIONS) + 1)
    out = {}
    for province in PROVINCES:
        values = table[province]
        if sum(values[:-1]) != values[-1]:
            raise SystemExit(f"zimbabwe: {province} religions sum to {sum(values[:-1]):,} "
                             f"against a printed {values[-1]:,}")
        out[province] = dict(zip(RELIGIONS, values[:-1])) | {"TOTAL": values[-1]}
    national = table["Total"]
    for i, label in enumerate(RELIGIONS + ["TOTAL"]):
        if sum(out[p][label] for p in PROVINCES) != national[i]:
            raise SystemExit(f"zimbabwe: {label} across provinces is not the printed total")
    return out


def read_language(text: str) -> dict[str, dict[str, int]]:
    table = table_page(text, "Table 2.17", list(LANGUAGES) + ["Total"], len(PROVINCES) + 1)
    out: dict[str, dict[str, int]] = {p: {} for p in PROVINCES}
    for raw, label in LANGUAGES.items():
        values = table[raw]
        if sum(values[:-1]) != values[-1]:
            raise SystemExit(f"zimbabwe: {raw} across provinces sums to {sum(values[:-1]):,} "
                             f"against a printed {values[-1]:,}")
        for province, n in zip(PROVINCES, values):
            out[province][label] = n
    for province, total in zip(PROVINCES, table["Total"]):
        if sum(out[province].values()) != total:
            raise SystemExit(f"zimbabwe: {province} languages sum to "
                             f"{sum(out[province].values()):,} against a printed {total:,}")
        out[province]["TOTAL"] = total
    return out


def build(text: str) -> list[dict[str, Any]]:
    fields = {"religion": read_religion(text), "language": read_language(text)}
    src = [{"field": "religion/language", "name": SOURCE, "url": URL, "license": LICENCE}]
    from common import slugify
    records = []
    for province in PROVINCES:
        values: dict[str, Any] = {}
        for field, table in fields.items():
            entry = table[province]
            values[field] = shares({k: v for k, v in entry.items() if k != "TOTAL" and v},
                                   total=entry["TOTAL"])
            values[f"{field}_year"] = YEAR
            values[f"{field}_note"] = f"{SOURCE}. {NOTES[field]}"
        records.append(record(f"ZWE-{slugify(province)}", province, level="admin1",
                              parent="ZWE", country="ZWE", sources=src, **values))
    return records


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--text", default=None, help="a saved probe_pdf dump instead of the PDF")
    args = ap.parse_args()
    log(f"zimbabwe: {SOURCE}")
    text = Path(args.text).read_text(encoding="utf-8") if args.text else fetch_text(URL)
    records = build(text)
    log(f"  {len(records)} provinces")
    if len(records) != 10:
        raise SystemExit(f"zimbabwe: expected 10 provinces, built {len(records)}")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
