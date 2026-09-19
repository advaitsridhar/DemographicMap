#!/usr/bin/env python3
"""Hong Kong: ethnicity and usual spoken language from the 2021 Population Census.

Hong Kong is one first-level shape on this map, drawn under China, and its
census is not China's: the Census and Statistics Department runs its own
count every ten years and asks ethnicity and usual spoken language, which
the mainland census does not. Religion it does not ask, and the shape's
religion stays declared not collected under the China policy.

The figures are the *2021 Population Census -- Main Results* (C&SD,
December 2022). The Department publishes the report as a PDF and, beside
it on the same page, the same tables as one workbook, 161 sheets, one per
table. The workbook is what this reads: the PDF sets each table without
ruling lines, so nothing finds a table on its pages, and a text reader
prints the row labels apart from the figures. Two sheets are read:

* **Table 3.9 (3)** -- *Population by sex, ethnicity and age group, 2021*,
  the both-sexes block. Chinese, then the non-Chinese groups as the
  census prints them: Filipino, Indonesian, South Asian (with Indian,
  Nepalese, Pakistani and "Other South Asian" beneath it), Thai, Japanese,
  Korean, Other Asian, White and "Others". "South Asian" is the sum of its
  four detail rows and is not written, so the population is counted once;
  "Others" -- which the table's note says includes people reporting more
  than one ethnicity -- is written as "Other ethnic groups".
* **Table 3.13** -- *Population aged 5 and over by usual spoken language and
  place of birth, 2021*, whose Total column is the whole composition:
  Cantonese, English, Putonghua, Fukien, Hakka, Chiu Chau, Other Chinese
  dialects, Filipino (Tagalog), Indonesian (Bahasa Indonesia), Japanese and
  Others. Usual spoken language is the language a person speaks at home;
  the population is aged 5 and over and excludes mute persons, and
  ``language_basis`` says so. (Table 3.12, the language table a reader
  meets first, is the share *able to speak* eleven selected languages, and
  those shares do not partition anyone.)

Every row's figure is checked as it is read: the leaves of the ethnicity
table must sum to its printed total and the South Asian rows to their
printed sub-total; the language rows must sum to their printed total; and
the shares that follow must sum to 100 within three tenths, with Chinese at
91.6 and Cantonese at 88.2, the two figures the report's text states in so
many words (paragraphs 3.18 and 3.24). Any of those failing is a refusal,
because a sheet that has moved a column is not a figure to publish.

Usage:
    python -m scripts.fetch_census.hongkong_census
    python -m scripts.fetch_census.hongkong_census --workbook main-results.xlsx
"""

from __future__ import annotations

import argparse
import io
import re
import sys
from pathlib import Path
from typing import Any

from ._shared import PROCESSED, http_get, log, record, shares, write_json

OUT = "hongkong_census.json"
YEAR = 2021
NAME = "Hong Kong Special Administrative Region"
URL = "https://www.census2021.gov.hk/doc/pub/21c-main-results.xlsx"
REPORT = "https://www.census2021.gov.hk/doc/pub/21c-main-results.pdf"
SOURCE = ("Census and Statistics Department, Hong Kong SAR, 2021 Population Census: "
          "Main Results (December 2022)")
LICENCE = ("Hong Kong Government; reproduction permitted with acknowledgement of "
           "the Census and Statistics Department as the source")
ETHNICITY_SHEET = "Table 3.9 (3)"
LANGUAGE_SHEET = "Table 3.13"
LANGUAGE_BASIS = "usual spoken language, population aged 5 and over"
TOLERANCE = 0.3
# What the report's own text says, and what the read must reproduce.
CHINESE_SHARE = 91.6
CANTONESE_SHARE = 88.2

# The census's labels, as the workbook prints them, to the map's words.
# Everything else is kept as printed, singular, without "people".
ETHNICITY_LABELS = {"Others": "Other ethnic groups"}
LANGUAGE_LABELS = {"Others": "Other languages"}
# Rows that are a sum of the rows beneath them, or of the whole table.
ETHNICITY_PARENTS = ("South Asian",)
TOTALS = ("Total", "Sub-total")
NOTE_MARK = re.compile(r"\s*\[\d+\]\s*$")
CJK = re.compile(r"[㐀-鿿]")


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.replace(",", "").replace(" ", "").strip()
        if re.fullmatch(r"-?\d+(\.\d+)?", text):
            return float(text)
    return None


def _label(cells: list[Any]) -> tuple[int, str] | None:
    """(column, text) of the first cell holding a label, or None."""
    for column, cell in enumerate(cells):
        if isinstance(cell, str) and cell.strip():
            return column, NOTE_MARK.sub("", cell.strip())
    return None


def paired_rows(rows: list[list[Any]]) -> list[tuple[int, str, list[float]]]:
    """(column, English label, figures) for every figure row of a sheet.

    The workbook writes each row twice: the Chinese label with the figures
    beside it, and the English label alone on the row beneath. A row is a
    figure row when its label is Chinese and figures follow; its name is
    the first label on the next row, which must not itself carry figures.
    """
    out = []
    for i, cells in enumerate(rows[:-1]):
        head = _label(cells)
        if not head or not CJK.search(head[1]):
            continue
        column, _ = head
        figures = [n for n in (_number(c) for c in cells[column + 1:]) if n is not None]
        if not figures:
            continue
        nxt = _label(rows[i + 1])
        if not nxt or CJK.search(nxt[1]):
            raise SystemExit(f"hongkong_census: no English label under row {i + 1} "
                             f"({head[1]!r})")
        if any(_number(c) is not None for c in rows[i + 1][nxt[0] + 1:]):
            raise SystemExit(f"hongkong_census: the row under {head[1]!r} carries "
                             f"figures of its own")
        out.append((column, nxt[1], figures))
    return out


def read_ethnicity(rows: list[list[Any]]) -> tuple[dict[str, int], dict[str, float]]:
    """({group: count}, {group: printed share}) for the both-sexes block of Table 3.9."""
    block = paired_rows(rows)
    if not any(isinstance(c, str) and c.strip() == "Both sexes"
               for cells in rows for c in cells):
        raise SystemExit("hongkong_census: the ethnicity sheet has no 'Both sexes' block")
    counts: dict[str, int] = {}
    printed: dict[str, float] = {}
    parents: dict[str, int] = {}
    totals: dict[str, int] = {}
    detail: dict[int, int] = {}
    for column, label, figures in block:
        # Five age groups, the total, and its share of the sex group's total.
        if len(figures) != 7:
            raise SystemExit(f"hongkong_census: {label!r} has {len(figures)} figures, "
                             "not five age groups, a total and a share")
        total = int(figures[5])
        if label in TOTALS:
            totals[label] = total
        elif label in ETHNICITY_PARENTS:
            parents[label] = total
            detail[column + 1] = 0
        else:
            name = ETHNICITY_LABELS.get(label, label)
            if name in counts:
                raise SystemExit(f"hongkong_census: {name!r} appears twice")
            counts[name] = total
            printed[name] = figures[6]
            if column in detail:
                detail[column] += total
    for parent, total in parents.items():
        beneath = sum(detail.values())
        if beneath != total:
            raise SystemExit(f"hongkong_census: {parent} prints {total:,} and its "
                             f"detail rows sum to {beneath:,}")
    if "Total" not in totals:
        raise SystemExit("hongkong_census: the ethnicity sheet has no Total row")
    if sum(counts.values()) != totals["Total"]:
        raise SystemExit(f"hongkong_census: ethnicity rows sum to {sum(counts.values()):,} "
                         f"against a printed total of {totals['Total']:,}")
    if "Sub-total" in totals and sum(counts.values()) - counts.get("Chinese", 0) \
            != totals["Sub-total"]:
        raise SystemExit("hongkong_census: the non-Chinese rows do not sum to the "
                         "printed sub-total")
    return counts, printed


def read_language(rows: list[list[Any]]) -> tuple[dict[str, int], dict[str, float]]:
    """({language: count}, {language: printed share}) from Table 3.13's Total column."""
    counts: dict[str, int] = {}
    printed: dict[str, float] = {}
    total: int | None = None
    for _column, label, figures in paired_rows(rows):
        # Three places of birth and the total, each a number and a share.
        if len(figures) != 8:
            raise SystemExit(f"hongkong_census: {label!r} has {len(figures)} figures, "
                             "not four number-and-share pairs")
        count, share = int(figures[6]), figures[7]
        if label in TOTALS:
            total = count
            continue
        name = LANGUAGE_LABELS.get(label, label)
        if name in counts:
            raise SystemExit(f"hongkong_census: {name!r} appears twice")
        counts[name] = count
        printed[name] = share
    if total is None:
        raise SystemExit("hongkong_census: the language sheet has no Total row")
    if sum(counts.values()) != total:
        raise SystemExit(f"hongkong_census: language rows sum to {sum(counts.values()):,} "
                         f"against a printed total of {total:,}")
    return counts, printed


def checked(field: str, counts: dict[str, int], anchor: str, expected: float,
            printed: dict[str, float]) -> list[dict[str, Any]]:
    """Shares from the counts, refused unless they are the whole population.

    The shares are computed from the counts, as every file here computes
    them, and then held against the column the census prints beside them:
    a row whose count and share disagree is a column read wrong.
    """
    rows = shares(counts)
    total = sum(r["pct"] for r in rows)
    if abs(total - 100.0) > TOLERANCE:
        raise SystemExit(f"hongkong_census: {field} shares sum to {total:.1f}, not 100")
    by_name = {r["group"]: r["pct"] for r in rows}
    if by_name.get(anchor) != expected:
        raise SystemExit(f"hongkong_census: {anchor} comes out at {by_name.get(anchor)}, "
                         f"not the {expected} the report states")
    for name, share in printed.items():
        if abs(by_name[name] - share) > 0.1:
            raise SystemExit(f"hongkong_census: {name} computes to {by_name[name]} "
                             f"against a printed {share}")
    return rows


def sheet_rows(workbook: Any, name: str) -> list[list[Any]]:
    if name not in workbook.sheetnames:
        raise SystemExit(f"hongkong_census: no sheet {name!r} in the workbook "
                         f"({len(workbook.sheetnames)} sheets)")
    return [list(row) for row in workbook[name].iter_rows(values_only=True)]


def build(blob: bytes) -> list[dict[str, Any]]:
    import openpyxl
    from common import slugify

    workbook = openpyxl.load_workbook(io.BytesIO(blob), read_only=True, data_only=True)
    counts, printed = read_ethnicity(sheet_rows(workbook, ETHNICITY_SHEET))
    ethnicity = checked("ethnicity", counts, "Chinese", CHINESE_SHARE, printed)
    counts, printed = read_language(sheet_rows(workbook, LANGUAGE_SHEET))
    language = checked("language", counts, "Cantonese", CANTONESE_SHARE, printed)
    workbook.close()
    log(f"  ethnicity: {len(ethnicity)} groups over {sum(r['count'] for r in ethnicity):,} "
        f"people; language: {len(language)} over {sum(r['count'] for r in language):,} "
        "aged 5 and over")
    sources = [
        {"field": "ethnicity", "name": f"{SOURCE}, Table 3.9", "url": URL,
         "license": LICENCE},
        {"field": "language", "name": f"{SOURCE}, Table 3.13", "url": URL,
         "license": LICENCE},
    ]
    return [record(
        f"CHN-{slugify(NAME)}", NAME, level="admin1", parent="CHN", country="CHN",
        aliases=["Hong Kong", "Hong Kong SAR", "Xianggang", "香港"],
        sources=sources,
        ethnicity=ethnicity, ethnicity_year=YEAR,
        ethnicity_note=(
            f"{SOURCE}, Table 3.9 (population by sex, ethnicity and age group), both "
            "sexes, read from the Department's workbook of the report's tables "
            f"({REPORT} is the report). Ethnicity as reported by the person; the "
            "census's 'South Asian' is the sum of Indian, Nepalese, Pakistani and "
            "'Other South Asian' (Bangladeshi and Sri Lankan) and is not repeated; "
            "'Other ethnic groups' is the census's 'Others', which includes people "
            "reporting more than one ethnicity. Hong Kong's own census, not China's: "
            "the mainland census records the 56 official nationalities and is not "
            "taken in the Special Administrative Region."),
        language=language, language_year=YEAR, language_basis=LANGUAGE_BASIS,
        language_note=(
            f"{SOURCE}, Table 3.13 (population aged 5 and over by usual spoken "
            "language and place of birth), the Total column, read from the "
            "Department's workbook of the report's tables. Usual spoken language is "
            "the language a person usually speaks at home, one per person, for the "
            "population aged 5 and over, excluding mute persons -- not the share "
            "able to speak a language, which the report's Table 3.12 gives and which "
            "adds to more than 100. Labels as the census prints them; 'Other "
            "languages' is its 'Others'."),
    )]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workbook", default=None,
                    help="a saved copy of the Main Results workbook instead of fetching it")
    args = ap.parse_args()
    log(f"hongkong_census: {SOURCE}")
    if args.workbook:
        blob = Path(args.workbook).read_bytes()
    else:
        blob = http_get(URL, binary=True, timeout=300)
        assert isinstance(blob, bytes)
    log(f"  {len(blob):,} bytes")
    records = build(blob)
    write_json(PROCESSED / OUT, records)
    log(f"  wrote {len(records)} record to {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
