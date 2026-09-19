#!/usr/bin/env python3
"""China: religion by province, tabulated from CFPS microdata for the five
provinces the survey can speak for.

The China Family Panel Studies asks adults "请问您属于什么宗教?" with seven
answers -- Buddhism, Taoism, Islam, Protestant, Catholic, none, other -- in
its 2012 and 2016 waves (2014 asked instead which deities a person believes
in, which is a different question and is not read; 2018 and 2020 ask only
about membership of a religious organisation). The 2016 stem is "您信仰什么
宗教" -- believe in, where 2012 said belong to -- and takes more than one
answer; the first is counted, and the note says so, because shares rose in
every province between the waves and the wording is part of why. A re-upload of the public-release
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
is written, the 2012 file is tabulated and compared with Table 2 of that
report, which prints the five provinces' shares and sample sizes. The
report's table turns out to be *unweighted*: an unweighted tabulation of the
2012 file reproduces every province within a quarter of a point, and no
weighting comes closer than half a point (Shanghai's Buddhism is 10.4%
unweighted and 8.3% with the cross-sectional weight). So the check is the
unweighted one, which proves the province codes and the non-answer rule,
with the sample sizes allowed to differ by the few respondents the 201906
re-release adds or drops. If it fails, nothing is written.

**What is written is weighted.** The cross-sectional individual weight
(``rswt_natcs``) is what CFPS publishes for population estimates, and within
a self-representative province it is valid for the province; respondents
who carry no weight -- entrants since the 2010 baseline -- are not in it,
and the sample size in each note counts only those who are. The note says
that the paper's own figure is unweighted, so a reader who compares the two
sees a method and not a disagreement.

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
SHARE_TOLERANCE = 0.5     # points, unweighted 2012 against the paper's printed shares
N_TOLERANCE = 0.01        # the 201906 re-release differs from the 2013 one by a few rows


def tabulate(rows: list[tuple[int, int, float]], *, weighted: bool = True
             ) -> dict[int, dict[str, Any]]:
    """{province code: {"n": respondents counted, "shares": {group: %}}}.

    ``rows`` are (province, answer code, weight). A negative answer code is a
    non-answer (missing, refused, not applicable, don't know) and is left
    out of both the count and the denominator, as the paper's tables do.
    Weighted, a respondent with no positive weight is left out too;
    unweighted, every valid answer counts once.
    """
    n: dict[int, int] = defaultdict(int)
    weight: dict[int, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for prov, code, w in rows:
        if code not in CODES:
            continue
        if weighted and (w is None or w <= 0):
            continue
        n[prov] += 1
        weight[prov][CODES[code]] += w if weighted else 1.0
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
    """The unweighted 2012 tabulation must reproduce the report's Table 2.

    ``table`` is tabulate(..., weighted=False). Sample sizes may differ by
    the re-release's few rows; shares may not differ by more than half a
    point. Either failing means the province codes or the non-answer rule
    are wrong, and nothing is written.
    """
    by_name = {name: (shares, n) for name, _, shares, n in PAPER_TABLE}
    worst_n = worst_share = 0.0
    for code in sorted(SELF_REPRESENTATIVE):
        name = PROVINCES[code]
        printed, n_printed = by_name[name]
        got = table.get(code)
        if got is None:
            raise SystemExit(f"cfps_microdata: 2012 has no rows for {name}")
        drift = abs(got["n"] - n_printed) / n_printed
        if drift > N_TOLERANCE:
            raise SystemExit(f"cfps_microdata: 2012 {name}: {got['n']} respondents "
                             f"against the paper's {n_printed}; the province code mapping "
                             "or the non-answer rule is wrong")
        worst_n = max(worst_n, drift)
        for group, pct in zip(PAPER_GROUPS, printed):
            gap = abs(got["shares"].get(group, 0.0) - pct)
            if gap > SHARE_TOLERANCE:
                raise SystemExit(f"cfps_microdata: 2012 {name} {group}: "
                                 f"{got['shares'].get(group, 0.0)} against the paper's {pct}")
            worst_share = max(worst_share, gap)
    log(f"  unweighted 2012 tabulation reproduces the report's Table 2: sample sizes "
        f"within {worst_n:.1%}, every share within {worst_share:.2f} points")


def diagnose(root: Path) -> None:
    """Which reading of the 2012 file reproduces the paper's Table 2?

    The first run refused: Liaoning came out at 2,810 respondents against the
    paper's 2,939. Rather than guess which rule differs -- the weight column,
    whether rows without a weight count, whether non-answers sit in the
    denominator -- every combination is printed against the paper.
    """
    import pandas as pd
    path = root / "cfps2012adult_201906.dta"
    weights = ["rswt_natcs12", "rswt_rescs12", "rswt_natpn1012", "rswt_respn1012"]
    df = pd.read_stata(str(path), columns=["provcd", "qm601", *weights],
                       convert_categoricals=False)
    by_name = {name: (shares, n) for name, _, shares, n in PAPER_TABLE}
    for code in sorted(SELF_REPRESENTATIVE):
        name = PROVINCES[code]
        printed, n_printed = by_name[name]
        prov = df[df["provcd"] == code]
        valid = prov[prov["qm601"].isin(list(CODES))]
        log(f"  {name}: paper n={n_printed}; rows in province={len(prov)}, "
            f"valid answers={len(valid)}, answered at all (incl. DK/refused)="
            f"{int((prov['qm601'] > -10).sum())}, "
            f"with each weight>0: "
            + ", ".join(f"{w[5:]}={int((valid[w] > 0).sum())}" for w in weights))
        target = dict(zip(PAPER_GROUPS, printed))

        def score(sub, w=None):
            tot = len(sub) if w is None else sub[w].sum()
            got = {g: 0.0 for g in PAPER_GROUPS}
            for k, g in CODES.items():
                part = sub[sub["qm601"] == k]
                got[g] = (len(part) if w is None else part[w].sum()) / tot * 100
            return max(abs(got[g] - target[g]) for g in PAPER_GROUPS), got

        for label, w, sub in [("unweighted, all valid", None, valid)] + [
                (f"{w[5:]} (rows with it)", w, valid[valid[w] > 0]) for w in weights]:
            gap, got = score(sub, w)
            log(f"      {label:32} n={len(sub):>5}  max |diff|={gap:5.2f}  "
                + " ".join(f"{g[:4]}={got[g]:.1f}" for g in PAPER_GROUPS))


def download() -> Path:
    os.environ.setdefault("TQDM_DISABLE", "1")
    import kagglehub
    return Path(kagglehub.dataset_download(DATASET))


def build(root: Path) -> tuple[int, list[dict[str, Any]]]:
    from common import slugify
    # Self-check first, on the wave the paper printed.
    y2012 = [w for w in WAVES if w[0] == 2012][0]
    rows2012 = read_wave(root, *y2012[1:])
    check_against_paper(tabulate(rows2012, weighted=False))
    w2012 = tabulate(rows2012, weighted=True)
    log("  2012 weighted, for comparison with the paper's unweighted table:")
    for code in sorted(SELF_REPRESENTATIVE):
        top = sorted(w2012[code]["shares"].items(), key=lambda kv: -kv[1])[:3]
        log(f"      {PROVINCES[code]:24} n={w2012[code]['n']:>5}  "
            + ", ".join(f"{g} {p}" for g, p in top))
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
    table = tabulate(rows, weighted=True)
    plain = tabulate(rows, weighted=False)
    log(f"  {year}: {len(rows):,} adult rows, {len(table)} provinces with answers")
    log("  every province, weighted shares with weighted n, then unweighted n "
        "(only the five self-representative ones, marked *, are written):")
    for code in sorted(table, key=lambda c: -table[c]["n"]):
        mark = "*" if code in SELF_REPRESENTATIVE else " "
        top = sorted(table[code]["shares"].items(), key=lambda kv: -kv[1])[:4]
        log(f"   {mark} {PROVINCES.get(code, code):36} n={table[code]['n']:>5} "
            f"(unweighted {plain.get(code, {}).get('n', 0):>5})  "
            + ", ".join(f"{g} {p}" for g, p in top))
    src = [{"field": "religion",
            "name": (f"China Family Panel Studies {year} adult questionnaire, religious "
                     f"affiliation (qm601) by province, tabulated with the wave's "
                     f"cross-sectional individual weight ({w_col}) from the public-release file"),
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
                f"province-level inference; the other provinces are not written. "
                f"Weighted by {w_col}, counting the {t['n']:,} respondents who carry it. "
                f"The same reading of the 2012 file, unweighted, reproduces Table 2 of "
                f"Lu Yunfeng's report ({PAPER_URL}) within {SHARE_TOLERANCE} points in "
                f"every share, which is how the province codes are known to be right; "
                f"that published table is unweighted, so it and this figure differ by "
                f"the weight and not by the data. "
                + ("The 2016 questionnaire asks which religion a person believes in "
                   "(信仰) where 2012 asked which they belong to (属于), and allows more "
                   "than one answer, of which the first is counted; shares rose in every "
                   "province between the two waves, and part of that rise is the wording. "
                   if year == 2016 else "")
                + "Affiliation, not practice.")))
    return year, out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=None, help="an already-extracted copy of the bundle")
    ap.add_argument("--diagnose", action="store_true",
                    help="print every reading of 2012 against the paper's Table 2, write nothing")
    args = ap.parse_args()
    log(f"cfps_microdata: {DATASET}")
    root = Path(args.root) if args.root else download()
    if args.diagnose:
        diagnose(root)
        return 0
    year, records = build(root)
    log(f"  {len(records)} provinces written from the {year} wave")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    sys.exit(main())
