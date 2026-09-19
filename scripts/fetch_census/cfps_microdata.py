#!/usr/bin/env python3
"""China: religion by province, tabulated from CFPS microdata for the five
provinces the survey can speak for.

The China Family Panel Studies asks adults "请问您属于什么宗教?" with seven
answers -- Buddhism, Taoism, Islam, Protestant, Catholic, none, other -- in
its 2012 and 2016 waves (2014 asked instead which deities a person believes
in, which is a different question and is not read; 2018 asks only about
membership of a religious organisation). A re-upload of the public-release
files sits on Kaggle. This reads the newest wave that carries the
affiliation question, weights each answer by the wave's cross-sectional
individual weight, and writes one row per province.

**Only five provinces are written.** CFPS drew Shanghai, Liaoning, Henan,
Gansu and Guangdong as independent, self-representative subsamples of 1,600
households each; the other twenty provinces were drawn from one pooled
frame that represents the pool and not its members, and the survey's own
report (Lu Yunfeng, 世界宗教文化 2014 no. 1, p. 12) says province-level
inference is supported for the five alone. The others are tabulated and
printed in the log with their sample sizes, so a reader can see them, and
are not written: a figure the survey says it cannot support is not a figure.

**The reader checks itself against the published table.** Before anything
is written, the 2012 file is tabulated the same way and compared with Table
2 of that report, which prints the five provinces' shares and sample sizes.
The unweighted counts must match exactly -- which proves the province code
mapping -- and the weighted shares within half a point, which proves the
weight. If either fails, nothing is written.

Provenance: CFPS is produced and distributed by Peking University's
Institute of Social Science Survey under a data-use agreement; the Kaggle
bundle is a third party's re-upload and its standing is not verified here.
What is written is aggregate shares by province, not microdata, and the
source note says where they came from.

Usage (on a machine that reaches Kaggle; kagglehub reads KAGGLE_USERNAME and
KAGGLE_KEY from the environment, and this public bundle needs neither):
    python -m scripts.fetch_census.cfps_microdata
    python -m scripts.fetch_census.cfps_microdata --root /path/to/extracted   # already downloaded
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from ._shared import PROCESSED, log, record, write_json
from .cfps_survey import TABLE as PAPER_TABLE, GROUPS as PAPER_GROUPS, URL as PAPER_URL

OUT = "cfps_microdata_province.json"
DATASET = "edjngfebav/cfps201420162020-china-family-panel-studies"
KAGGLE_URL = f"https://www.kaggle.com/datasets/{DATASET}"

# The answer codes CFPS uses for affiliation, in the map's canonical words.
CODES = {1: "Buddhism", 2: "Taoism", 3: "Islam", 4: "Protestant",
         5: "Roman Catholic", 6: "No religion", 77: "Other religions"}

# Each wave that asks affiliation: file stem, province column, answer column,
# weight column. Newest first; the first whose file exists is read.
WAVES: list[tuple[int, str, str, str, str]] = [
    (2020, "cfps2020person_202306", "provcd20", "qm601_s_1", "rswt_natcs20n"),
    (2016, "cfps2016adult_201906", "provcd16", "qm601_s_1", "rswt_natcs16"),
    (2012, "cfps2012adult_201906", "provcd", "qm601", "rswt_natcs12"),
]

# GB/T 2260 province codes, as the boundary file names the shapes.
PROVINCES: dict[int, str] = {
    11: "Beijing Municipality", 12: "Tianjin Municipality", 13: "Hebei Province",
    14: "Shanxi Province", 15: "Inner Mongolia Autonomous Region",
    21: "Liaoning Province", 22: "Jilin Province", 23: "Heilongjiang Province",
    31: "Shanghai Municipality", 32: "Jiangsu Province", 33: "Zhejiang Province",
    34: "Anhui Province", 35: "Fujian Province", 36: "Jiangxi Province",
    37: "Shandong Province", 41: "Henan Province", 42: "Hubei Province",
    43: "Hunan Province", 44: "Guangdong", 45: "Guangxi Zhuang Autonomous Region",
    46: "Hainan Province", 50: "Chongqing Municipality", 51: "Sichuan Province",
    52: "Guizhou Province", 53: "Yunnan Province", 54: "Tibet Autonomous Region",
    61: "Shaanxi Province", 62: "Gansu Province", 63: "Qinghai Province",
    64: "Ningxia Hui Autonomous Region", 65: "Xinjiang Uyghur Autonomous Region",
}
SELF_REPRESENTATIVE = {31, 21, 41, 62, 44}
SHARE_TOLERANCE = 0.5     # points, against the paper's printed shares


def tabulate(rows: list[tuple[int, int, float]]) -> dict[int, dict[str, Any]]:
    """{province code: {"n": unweighted, "shares": {group: weighted %}}}.

    ``rows`` are (province, answer code, weight). A negative answer code is a
    non-answer (missing, refused, not applicable, don't know) and is left
    out of both the count and the denominator, as the paper's tables do.
    """
    n: dict[int, int] = defaultdict(int)
    weight: dict[int, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for prov, code, w in rows:
        if code not in CODES or w is None or w <= 0:
            continue
        n[prov] += 1
        weight[prov][CODES[code]] += w
    out = {}
    for prov in n:
        total = sum(weight[prov].values())
        out[prov] = {"n": n[prov],
                     "shares": {g: round(v / total * 100, 1) for g, v in weight[prov].items()}}
    return out


def read_wave(root: Path, stem: str, prov_col: str, ans_col: str, w_col: str
              ) -> list[tuple[int, int, float]]:
    import pandas as pd
    path = root / f"{stem}.dta"
    df = pd.read_stata(str(path), columns=[prov_col, ans_col, w_col],
                       convert_categoricals=False)
    df = df.dropna(subset=[prov_col, ans_col])
    return [(int(p), int(a), (None if pd.isna(w) else float(w)))
            for p, a, w in zip(df[prov_col], df[ans_col], df[w_col])]


def check_against_paper(table: dict[int, dict[str, Any]]) -> None:
    """The 2012 tabulation must reproduce the report's Table 2, or nothing is written."""
    by_name = {name: (shares, n) for name, _, shares, n in PAPER_TABLE}
    for code in sorted(SELF_REPRESENTATIVE):
        name = PROVINCES[code]
        printed, n_printed = by_name[name]
        got = table.get(code)
        if got is None:
            raise SystemExit(f"cfps_microdata: 2012 has no rows for {name}")
        if got["n"] != n_printed:
            raise SystemExit(f"cfps_microdata: 2012 {name}: {got['n']} respondents "
                             f"against the paper's {n_printed}; the province code mapping "
                             "or the non-answer rule is wrong")
        for group, pct in zip(PAPER_GROUPS, printed):
            mine = got["shares"].get(group, 0.0)
            if abs(mine - pct) > SHARE_TOLERANCE:
                raise SystemExit(f"cfps_microdata: 2012 {name} {group}: {mine} against the "
                                 f"paper's {pct}; the weight is wrong")
    log("  2012 tabulation reproduces the report's Table 2: sample sizes exactly, "
        f"shares within {SHARE_TOLERANCE} points")


def download() -> Path:
    os.environ.setdefault("TQDM_DISABLE", "1")
    import kagglehub
    return Path(kagglehub.dataset_download(DATASET))


def build(root: Path) -> tuple[int, list[dict[str, Any]]]:
    from common import slugify
    # Self-check first, on the wave the paper printed.
    y2012 = [w for w in WAVES if w[0] == 2012][0]
    check_against_paper(tabulate(read_wave(root, *y2012[1:])))
    # Then the newest wave that is there and carries the question.
    for year, stem, prov_col, ans_col, w_col in WAVES:
        if not (root / f"{stem}.dta").exists():
            log(f"  {year}: {stem}.dta is not in the bundle")
            continue
        try:
            rows = read_wave(root, stem, prov_col, ans_col, w_col)
        except (ValueError, KeyError) as e:
            log(f"  {year}: {stem}.dta lacks {ans_col} or {w_col} ({e}); not the affiliation question")
            continue
        break
    else:
        raise SystemExit("cfps_microdata: no wave carries the affiliation question")
    table = tabulate(rows)
    log(f"  {year}: {len(rows):,} adult rows, {len(table)} provinces with answers")
    log("  every province, weighted shares and unweighted n (only the five "
        "self-representative ones are written):")
    for code in sorted(table, key=lambda c: -table[c]["n"]):
        mark = "*" if code in SELF_REPRESENTATIVE else " "
        top = sorted(table[code]["shares"].items(), key=lambda kv: -kv[1])[:4]
        log(f"   {mark} {PROVINCES.get(code, code):36} n={table[code]['n']:>5}  "
            + ", ".join(f"{g} {p}" for g, p in top))
    src = [{"field": "religion",
            "name": (f"China Family Panel Studies {year} adult questionnaire, religious "
                     f"affiliation (qm601) by province, tabulated with the wave's "
                     f"cross-sectional individual weight from the public-release file"),
            "url": KAGGLE_URL,
            "license": ("CFPS is distributed by Peking University's Institute of Social "
                        "Science Survey under a data-use agreement; the file was read from "
                        "a third-party re-upload on Kaggle and only aggregate shares are "
                        "kept")}]
    out = []
    for code in sorted(SELF_REPRESENTATIVE):
        t = table[code]
        shares = [{"group": g, "pct": p} for g, p in t["shares"].items() if p > 0]
        shares.sort(key=lambda s: s["pct"], reverse=True)
        name = PROVINCES[code]
        out.append(record(
            f"CHN-{slugify(name)}", name, level="admin1", parent="CHN", country="CHN",
            sources=src, religion=shares, religion_year=year,
            religion_note=(
                f"{src[0]['name']}. A survey of adults, not a census: China's census "
                f"does not ask religion. Self-declared affiliation, {t['n']:,} "
                f"respondents in this province, which CFPS draws as an independent, "
                f"self-representative subsample -- one of five provinces (Shanghai, "
                f"Liaoning, Henan, Gansu, Guangdong) for which the survey supports "
                f"province-level inference; the other provinces are not written. The "
                f"same reading of the 2012 file reproduces the published Table 2 of "
                f"Lu Yunfeng's report ({PAPER_URL}) exactly in sample size and within "
                f"{SHARE_TOLERANCE} points in every share. Affiliation, not practice.")))
    return year, out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=None, help="an already-extracted copy of the bundle")
    args = ap.parse_args()
    log(f"cfps_microdata: {DATASET}")
    root = Path(args.root) if args.root else download()
    year, records = build(root)
    log(f"  {len(records)} provinces written from the {year} wave")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    sys.exit(main())
