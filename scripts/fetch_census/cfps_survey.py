#!/usr/bin/env python3
"""China: religion by province for the five provinces CFPS 2012 sampled on their own.

China's census does not ask religion, and the map says so on every province.
The best figure by province is a survey: the China Family Panel Studies
(CFPS, Peking University's Institute of Social Science Survey) asked a
religion module in its 2012 wave, and Lu Yunfeng's report on it -- *当代中国
宗教状况报告——基于 CFPS (2012) 调查数据*, 世界宗教文化 2014 no. 1, pp.
11-25, reached through the Internet Archive from the CASS Institute of World
Religions' site -- prints affiliation by province for the five provinces the
survey drew as independent, self-representative subsamples of 1,600
households each: Shanghai, Liaoning, Henan, Gansu and Guangdong. The paper
says (p. 12) that only those five support province-level inference; the
other twenty provinces were drawn from one pooled frame and are not read.

Table 2 (p. 13) is transcribed here, because the PDF is InDesign's vector
outlines with no text layer and nothing can parse it; the figures were read
from the rendered page. Each column must sum to 100.0 within a tenth, and
the sample sizes are carried.

What the figure is: self-declared affiliation of adults ("请问您属于什么宗
教?"), seven options, weighted. What it is not: a census, or a count of
practice -- the same paper finds under 1% of Shanghai's respondents in any
religious organisation. The survey excluded Xinjiang, Tibet, Qinghai, Inner
Mongolia, Ningxia and Hainan, so its national figure understates Islam and
Tibetan Buddhism; that does not touch these five provinces, and the national
row is not written.

Usage:
    python -m scripts.fetch_census.cfps_survey
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

from ._shared import PROCESSED, log, record, write_json

OUT = "cfps_survey_province.json"
YEAR = 2012
URL = ("https://web.archive.org/web/20140809051625/"
       "http://iwr.cass.cn/zjwh/201403/W020140303370398758556.pdf")
SOURCE = ("Lu Yunfeng (Peking University Institute of Religion and Culture), "
          "当代中国宗教状况报告——基于CFPS(2012)调查数据, 世界宗教文化 2014(1), "
          "Table 2: religious affiliation of adults in five provinces, "
          "China Family Panel Studies 2012")
LICENCE = "cited for research with attribution; the PDF is not redistributed"

# Table 2 as printed, per province: (shape name, aliases, shares, sample size).
# The labels are the paper's seven options in the map's canonical words.
GROUPS = ["Buddhism", "Taoism", "Islam", "Protestant", "Roman Catholic",
          "No religion", "Other religions"]
TABLE: list[tuple[str, tuple[str, ...], list[float], int]] = [
    ("Shanghai Municipality", ("Shanghai", "上海"),
     [10.4, 0.1, 0.0, 1.9, 0.7, 86.7, 0.1], 2362),
    ("Liaoning Province", ("Liaoning", "辽宁"),
     [5.5, 0.0, 0.8, 2.1, 0.1, 91.3, 0.1], 2939),
    ("Henan Province", ("Henan", "河南"),
     [6.4, 0.1, 1.3, 5.6, 0.5, 86.0, 0.2], 3874),
    ("Gansu Province", ("Gansu", "甘肃"),
     [8.2, 1.0, 3.4, 0.4, 0.1, 87.0, 0.0], 3873),
    ("Guangdong", ("Guangdong Province", "广东"),
     [6.2, 0.2, 0.0, 0.8, 0.2, 92.5, 0.0], 2869),
]
TOLERANCE = 0.15   # a column of seven figures to one decimal


def check(name: str, shares: list[float]) -> None:
    """A transcribed column must still be the whole population."""
    total = sum(shares)
    if abs(total - 100.0) > TOLERANCE:
        raise SystemExit(f"cfps_survey: {name} sums to {total:.1f}, not 100")
    if len(shares) != len(GROUPS) or any(s < 0 for s in shares):
        raise SystemExit(f"cfps_survey: {name} has a malformed column")


def build() -> list[dict[str, Any]]:
    from common import slugify
    src = [{"field": "religion", "name": SOURCE, "url": URL, "license": LICENCE}]
    out = []
    for name, aliases, shares, n in TABLE:
        check(name, shares)
        rows = [{"group": g, "pct": p} for g, p in zip(GROUPS, shares) if p > 0]
        rows.sort(key=lambda r: r["pct"], reverse=True)
        out.append(record(
            f"CHN-{slugify(name)}", name, level="admin1", parent="CHN",
            country="CHN", aliases=list(aliases), sources=src,
            religion=rows, religion_year=YEAR,
            religion_note=(
                f"{SOURCE}. A survey of adults, not a census: China's census does "
                f"not ask religion. Self-declared affiliation from the CFPS 2012 "
                f"religion module, {n:,} respondents in this province, which the "
                f"survey drew as an independent, self-representative subsample of "
                f"1,600 households -- one of five provinces (Shanghai, Liaoning, "
                f"Henan, Gansu, Guangdong) for which the survey supports "
                f"province-level inference. Shares as printed in the paper's "
                f"Table 2; a group printed at 0.0% is omitted. Affiliation, not "
                f"practice: the same paper finds about 1% of respondents in any "
                f"religious organisation.")))
    return out


def main() -> int:
    argparse.ArgumentParser(description=__doc__,
                            formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    log(f"cfps_survey: {SOURCE}")
    records = build()
    log(f"  {len(records)} provinces transcribed from Table 2")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    sys.exit(main())
