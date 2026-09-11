#!/usr/bin/env python3
"""South Korea: religion by residence region, Hankook Research's 2025 pooled survey.

No census figure by province is reachable: the 2015 census asked religion
and KOSIS publishes it by province and district, but only through an API
that needs a registered key. Until that key exists, the best published
figure by region is a survey. Hankook Research's weekly report No. 358-3
(3 December 2025, *2025 Religion Perception Survey: religious population and
religious activity*) pools the religion question from the 22 waves of its
biweekly "Yeoron sok-ui Yeoron" web panel run January to November 2025:
23,000 adults aged 18 and over, weighted by region, sex and age to the
resident register. Page 8 crosses religion with seven residence regions:
Protestant, Catholic and Buddhist shares, "has a religion" and "no
religion", each as a whole percentage for 2024 and 2025 with the change.

What this reader does with it:

* the 2025 column is read; "other religion", which the page does not print
  by region, is the printed "has a religion" less the three named faiths,
  and must come out between 0 and 3 (the report puts it at 1% nationally);
* "has a religion" and "no religion" must sum to 100 in every row;
* the printed national row must agree, within one point, with the seven
  regions weighted by their share of the adult population as the report
  prints it on page 10 (Seoul 19, Incheon/Gyeonggi 32, Chungcheong 11,
  Honam 10, Daegu/Gyeongbuk 10, Busan/Ulsan/Gyeongnam 15, Gangwon/Jeju 4).

**The seven groupings are coarser than the seventeen provinces**, and this
map's rule elsewhere (the Bahamas' island groupings, India's split
districts) is that a figure coarser than the shape is not spread across the
shape's members. Korea is the stated exception, by the map owner's decision
on 11 September 2026, because nothing finer is reachable: each province
carries its grouping's figure, and its note says which grouping and how
many provinces share it. This is the lowest-authority file for Korea; a
census figure replaces it field by field when one is read.

The report is (c) Hankook Research, which permits citation of a small part
for research with attribution and forbids redistribution: seven rows of one
table are read from the report at its own URL, and the PDF is not stored.

Usage:
    python -m scripts.fetch_census.korea_survey
    python -m scripts.fetch_census.korea_survey --text dump.txt   # a saved probe_pdf dump
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

from ._shared import PROCESSED, log, record, write_json

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from probe_pdf import PAGE_BREAK, fetch_text  # noqa: E402

OUT = "korea_survey_province.json"
YEAR = 2025
# The report as the pollster posts it (archives/34782), its Korean file name
# percent-encoded so the URL is plain ASCII.
URL = ("https://hrcopinion.co.kr/wp-content/uploads/2025/12/"
       "358-3-%EB%B3%B4%EA%B3%A0%EC%84%9C_%ED%95%9C%EA%B5%AD%EB%A6%AC%EC%84%9C"
       "%EC%B9%98-%EC%A3%BC%EA%B0%84%EB%A6%AC%ED%8F%AC%ED%8A%B8_%EC%97%AC%EB%A"
       "1%A0%EC%86%8D%EC%9D%98%EC%97%AC%EB%A1%A0-%EC%A0%9C358-3%ED%98%B82025%E"
       "B%85%84-12%EC%9B%94-3%EC%9D%BC_%EC%A2%85%EA%B5%90%EC%9D%B8%EA%B5%AC-%E"
       "D%98%84%ED%99%A9%EA%B3%BC-%EC%A2%85%EA%B5%90-%ED%99%9C%EB%8F%99.pdf")
SOURCE = ("Hankook Research, 2025 Religion Perception Survey: religious population and "
          "religious activity (Weekly Report No. 358-3, 3 December 2025), religion by "
          "residence region")
LICENCE = ("(c) Hankook Research; citation of a small part for research is permitted with "
           "attribution, redistribution is not")

# The report's seven residence regions, in the order the table prints them,
# each with the provinces (as the boundary file names them) it groups, and its
# share of the adult population from the report's page 10.
GROUPINGS: list[tuple[str, str, list[str], int]] = [
    ("서울", "Seoul", ["Seoul"], 19),
    ("인천/경기", "Incheon/Gyeonggi", ["Incheon", "Gyeonggi"], 32),
    ("대전/세종/충청", "Daejeon/Sejong/Chungcheong",
     ["Daejeon", "Sejong", "North Chungcheong", "South Chungcheong"], 11),
    ("광주/전라", "Gwangju/Jeolla", ["Gwangju", "North Jeolla", "South Jeolla"], 10),
    ("대구/경북", "Daegu/Gyeongbuk", ["Daegu", "North Gyeongsang"], 10),
    ("부산/울산/경남", "Busan/Ulsan/Gyeongnam", ["Busan", "Ulsan", "South Gyeongsang"], 15),
    ("강원/제주", "Gangwon/Jeju", ["Gangwon", "Jeju"], 4),
]
NATIONAL = "전체"
# The five printed blocks, each "'24 '25 change": the 2025 value is the second.
COLUMNS = ["Protestant", "Roman Catholic", "Buddhism", "has_religion", "No religion"]
TOKEN = re.compile(r"^(?:[+-]?\d+|-)$")
# The column heads, compared with every space removed: one PDF reader keeps
# the spaces inside "개신교 신자" and another drops them.
MARKS = ["거주지역", "개신교신자", "천주교신자", "불교신자", "믿는종교없음"]


def page_of(text: str) -> str:
    """The page that crosses religion with the residence regions."""
    for page in text.split(PAGE_BREAK):
        flat = re.sub(r"\s+", "", page)
        if all(mark in flat for mark in MARKS) and all(k in flat for k, *_ in GROUPINGS):
            return page
    raise SystemExit("korea_survey: no page carries religion by residence region")


def row(tokens: list[str], label: str) -> dict[str, int]:
    """The 2025 shares on the row that starts with ``label``.

    The row is fifteen tokens: five blocks of 2024, 2025 and the change.
    The label is searched as a whole token, so a line break inside the row
    (which a PDF reader may add) does not matter.
    """
    for i, tok in enumerate(tokens):
        if tok != label:
            continue
        cells = tokens[i + 1:i + 16]
        if len(cells) == 15 and all(TOKEN.match(c) for c in cells):
            values = [int(cells[3 * j + 1]) for j in range(5)]
            return dict(zip(COLUMNS, values))
    raise SystemExit(f"korea_survey: no row of fifteen figures for {label}")


def read(text: str) -> dict[str, dict[str, float]]:
    """{grouping: {religion: percent}} for the seven regions, checked."""
    tokens = page_of(text).split()
    out: dict[str, dict[str, float]] = {}
    for korean, name, _, _ in GROUPINGS:
        r = row(tokens, korean)
        if r["has_religion"] + r["No religion"] != 100:
            raise SystemExit(f"korea_survey: {name}: has {r['has_religion']} + none "
                             f"{r['No religion']} is not 100")
        other = r["has_religion"] - r["Protestant"] - r["Roman Catholic"] - r["Buddhism"]
        if not 0 <= other <= 3:
            raise SystemExit(f"korea_survey: {name}: other religion comes out at {other}")
        out[name] = {"Protestant": float(r["Protestant"]),
                     "Roman Catholic": float(r["Roman Catholic"]),
                     "Buddhism": float(r["Buddhism"]),
                     "Other religions": float(other),
                     "No religion": float(r["No religion"])}
    national = row(tokens, NATIONAL)
    weight = sum(w for *_, w in GROUPINGS)
    for label in ("Protestant", "Roman Catholic", "Buddhism", "No religion"):
        rebuilt = sum(out[name][label] * w for _, name, _, w in GROUPINGS) / weight
        if abs(rebuilt - national[label]) > 1.0:
            raise SystemExit(f"korea_survey: {label} rebuilt from the regions is {rebuilt:.1f} "
                             f"against a printed national {national[label]}")
    return out


def build(text: str) -> list[dict[str, Any]]:
    table = read(text)
    src = [{"field": "religion", "name": SOURCE, "url": URL, "license": LICENCE}]
    from common import slugify
    records = []
    for _, name, provinces, _ in GROUPINGS:
        shares = [{"group": g, "pct": p} for g, p in table[name].items()]
        shares.sort(key=lambda s: s["pct"], reverse=True)
        members = (f"the only province in the report's residence region '{name}'"
                   if len(provinces) == 1 else
                   f"one of the {len(provinces)} provinces the report pools as the residence "
                   f"region '{name}' ({', '.join(provinces)}) and carries that region's figure, "
                   "by the map owner's decision, because no figure by province is reachable")
        for province in provinces:
            records.append(record(
                f"KOR-{slugify(province)}", province, level="admin1", parent="KOR",
                country="KOR", sources=src, religion=shares, religion_year=YEAR,
                religion_note=(
                    f"{SOURCE}. A survey of adults, not a census: the religion question "
                    "pooled from the 22 waves of Hankook Research's biweekly web panel run "
                    "January to November 2025, 23,000 respondents aged 18 and over, weighted "
                    "by region, sex and age to the resident register. Whole percentages as "
                    "printed; 'other religions' is the printed 'has a religion' less "
                    "Protestant, Catholic and Buddhist. "
                    f"This province is {members}. The 2015 census asked religion and KOSIS "
                    "publishes it by province behind a registered key; that figure replaces "
                    "this one when read.")))
    return records


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--text", default=None, help="a saved probe_pdf dump instead of the PDF")
    args = ap.parse_args()
    log(f"korea_survey: {SOURCE}")
    text = Path(args.text).read_text(encoding="utf-8") if args.text else fetch_text(URL)
    records = build(text)
    log(f"  {len(records)} provinces from {len(GROUPINGS)} residence regions")
    if len(records) != 17:
        raise SystemExit(f"korea_survey: expected 17 provinces, built {len(records)}")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    sys.exit(main())
