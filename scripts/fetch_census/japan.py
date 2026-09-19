#!/usr/bin/env python3
"""Japan: 47 prefectures resolved from secondary sources, by the owner's decision.

The Kokusei Chosa asks nationality and not religion, ethnicity or language,
and for as long as this map read only censuses the prefectures said so
(``docs/SOURCES.md``, "Japan and Turkey"). On 19 September 2026 the map's
owner decided that Japan should carry what secondary sources can say, the
way Korea's provinces carry a pollster's survey, provided every figure is
labelled for what it is. This module is that decision, built in three parts
that are three different kinds of thing.

**Ethnicity is nationality, read.** The 2020 census publishes population by
nationality for every prefecture (e-Stat table ``0003445244``, 令和２年国勢調査
人口等基本集計, 外国人 男女，国籍別人口), thirteen nationalities and the
Japanese, with a fourteenth row for people whose nationality the census
could not establish. The composition is written as a list -- it is a census
count -- under ``ethnicity_basis: "nationality"``, because a passport is not
an ethnicity: Japanese nationals include naturalised citizens and people of
any ancestry, and the Ainu, Ryukyuans and long-settled Koreans who hold
Japanese nationality are all "Japanese" here. The reader checks the table
against itself (the 47 prefectures must sum to its own 全国 row, the
thirteen nationalities to its foreign total) and refuses to write anything
if they do not: that is a table that is the wrong thing. It then checks the
全国 row against the national figures the Statistics Bureau printed in the
census's 結果の概要 (``PUBLISHED``): a composition more than half a point
away is also the wrong table, but a count that differs by less is published
and the difference goes into every prefecture's ``ethnicity_note`` in one
sentence, by the owner's instruction, rather than holding the prefectures
back over a summary.

**Religion is modelled.** Nothing counts religion by prefecture in a way
that partitions a population: the one official statistic, the Agency for
Cultural Affairs' 宗教統計調査 (``0003282963``), counts adherents as religious
corporations report them against the prefecture where each corporation is
registered, and sums to 175 million in a country of 124 million. It cannot
be a composition. It can be a *relative* signal, and that is all it is used
for here:

1. A national prior from a self-identification survey: NHK's 2018 ISSP
   "Religion" round (``PRIOR``), whose question is "ふだん信仰している宗教が
   ありますか" and whose answers were Buddhism 31%, Shinto 3%, Christianity
   1%, other 1%, no religion 62%, no answer 2%.
2. For each prefecture and each of the survey's four affiliated traditions,
   a tilt ratio: the tradition's share of that prefecture's reported
   adherents divided by its share of the nation's, clipped to
   [1/``TILT_BOUND``, ``TILT_BOUND``].
3. The prior's affiliated shares multiplied by their tilt ratios, then
   rescaled so they sum to the prior's affiliated total; "no religion" is
   held at the survey's national figure, since no source gives it by
   prefecture. The 2% who gave no answer are left out and the rest scaled
   to 100.
4. Absolute bounds (``CAPS``): no prefecture's Christianity or Shinto may
   exceed a stated share, because the signal's artefacts (Okinawa reports
   90% of its adherents as Shinto) would otherwise pass through the tilt.
   A group that hits its bound is held there and the rest rescaled.

Every prefecture's record carries the steps, the ratios, and which bound if
any was hit. **No backtest is possible** -- there is no prefecture-level
self-identification figure to score against -- so the estimate carries no
``backtest`` key, and its note says so. The five prefectures the tilt moves
furthest from the prior are printed in the log.

**Language is modelled** from the nationality composition, one step: every
person is taken to speak the majority home language of their nationality
(``LANGUAGE_OF``). That overstates Japanese-speaking among nobody and
understates it among everybody else -- a Korean national born in Osaka and
a Brazilian of Japanese descent both speak Japanese at home more often than
this assumes, and naturalised citizens' families the other way. The method
is named ``tier1-nationality-to-language`` and the note says what it is.

Usage:
    python -m scripts.fetch_census.japan            # needs ESTAT_API in the environment
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from ._shared import PROCESSED, log, measure, record, write_json

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import MODELLED, estimate, slugify  # noqa: E402
from probe_estat import app_id, call, listed, result_of  # noqa: E402

OUT = "japan_prefecture.json"
DECISION = "19 September 2026"
CENSUS_YEAR = 2020

# --- the census: nationality by prefecture --------------------------------
NATIONALITY_TABLE = "0003445244"
NATIONALITY_URL = f"https://www.e-stat.go.jp/dbview?sid={NATIONALITY_TABLE}"
NATIONALITY_SOURCE = ("Statistics Bureau of Japan, 2020 Population Census (令和２年国勢調査), "
                      "人口等基本集計: population by sex and nationality for Japan, prefectures "
                      f"and municipalities (e-Stat table {NATIONALITY_TABLE})")
ESTAT_LICENCE = ("e-Stat terms of use (compatible with CC BY 4.0): source to be credited")

# The table's 国籍 codes, in the map's words. The census prints 韓国，朝鮮 as
# one row -- the two Korean nationalities the Japanese register records --
# and 中国 as the census records it.
NATIONALITY_CODES: dict[str, str] = {
    "2": "Japanese",
    "101": "Korean", "102": "Chinese", "103": "Filipino", "104": "Thai",
    "105": "Indonesian", "106": "Vietnamese", "107": "Indian", "108": "Nepalese",
    "109": "British", "110": "American", "111": "Brazilian", "112": "Peruvian",
    "113": "Other nationalities",
}
CODE_TOTAL, CODE_FOREIGN, CODE_UNKNOWN = "0", "1", "3"

# The Statistics Bureau's printed national figures for the same census,
# read from 令和２年国勢調査 人口等基本集計結果 結果の概要 (30 November 2021),
# section IV, pages 33 and 35 (the runner's probe of PUBLISHED_URL). They are
# a different universe from the table: the 概要's headline counts are 不詳補完値,
# in which the 2,202,484 people recorded as neither Japanese nor foreign are
# allocated to one or the other, so its foreign population is 2,747,137 where
# the table records 2,402,460. The total population is the same count in both
# and must match exactly, or the table is the wrong thing; the imputed
# Japanese and foreign counts must sum to it; and the foreign share the
# imputation gives must sit within NATIONAL_TOLERANCE points of the share this
# composition gives, or the table is the wrong thing. Inside that tolerance
# the difference is published and stated on every prefecture in one sentence
# (``imputation_caveat``), by the owner's instruction of 19 September 2026.
# Section VII of the same document prints the nationalities; the probe's page
# cap stopped short of it, and no second probe was spent.
PUBLISHED_URL = "https://www.stat.go.jp/data/kokusei/2020/kekka/pdf/outline_01.pdf"
PUBLISHED: dict[str, int] = {
    "total": 126_146_099,
    "japanese_imputed": 123_398_962,
    "foreign_imputed": 2_747_137,
}
NATIONAL_TOLERANCE = 0.5     # points, foreign share: imputed against recorded
SUM_TOLERANCE = 0.3          # points, a prefecture's shares against 100

# --- the survey: the national prior -----------------------------------------
PRIOR_SOURCE = ("NHK Broadcasting Culture Research Institute, ISSP 2018 'Religion' survey of "
                "Japan (fieldwork 27 October to 4 November 2018, 2,400 adults aged 18 and over "
                "by drop-off/pick-up, 1,466 valid responses), as reported by Toshiyuki "
                "Kobayashi, 日本人の宗教的意識や行動はどう変わったか, 放送研究と調査, April 2019, "
                "pp. 52-72")
PRIOR_URL = "https://www.nhk.or.jp/bunken/research/yoron/pdf/20190401_7.pdf"
PRIOR_YEAR = 2018
# "ふだん信仰している宗教がありますか", whole percentages as printed on p. 53:
# Buddhism 31, Shinto 3, Christianity 1; any religion 36, so other is 1;
# no religion 62; the remaining 2 gave no answer.
PRIOR: dict[str, float] = {"Buddhism": 31.0, "Shinto": 3.0, "Christianity": 1.0,
                           "Other religions": 1.0}
PRIOR_NONE = 62.0
PRIOR_NO_ANSWER = 2.0

# --- the signal: adherents by prefecture ------------------------------------
BELIEVERS_TABLE = "0003282963"
BELIEVERS_URL = f"https://www.e-stat.go.jp/dbview?sid={BELIEVERS_TABLE}"
BELIEVERS_TIME = "2025100000"          # 2025年度: as of 31 December 2024
BELIEVERS_ASOF = "31 December 2024"
BELIEVERS_SOURCE = ("Agency for Cultural Affairs, 宗教統計調査 (Religious Statistics Survey), "
                    "believers (信者数) by prefecture and religious tradition as reported by "
                    f"religious corporations, at {BELIEVERS_ASOF} (e-Stat table {BELIEVERS_TABLE})")
# cat04, the 宗教系統, in the survey's words.
TRADITIONS: dict[str, str] = {"110": "Shinto", "120": "Buddhism",
                              "130": "Christianity", "140": "Other religions"}
TRADITION_TOTAL = "100"

# The tilt ratio is clipped to [1/TILT_BOUND, TILT_BOUND] before it touches
# the prior, and the two traditions the signal is known to misplace are held
# under an absolute share. Nagasaki, Japan's most Christian prefecture, is a
# few percent Christian by the churches' own counts; Shinto's national
# self-identification is 3%, and three times that is the most a registration
# count is allowed to move it.
TILT_BOUND = 3.0
CAPS: dict[str, float] = {"Christianity": 5.0, "Shinto": 9.0}

RELIGION_METHOD = "tier1-national-prior-tilted-by-adherents"
LANGUAGE_METHOD = "tier1-nationality-to-language"

# --- the assumption: a nationality's majority home language ----------------
LANGUAGE_OF: dict[str, str] = {
    "Japanese": "Japanese", "Korean": "Korean", "Chinese": "Chinese (Mandarin)",
    "Filipino": "Filipino", "Thai": "Thai", "Indonesian": "Indonesian",
    "Vietnamese": "Vietnamese", "Indian": "Hindi", "Nepalese": "Nepali",
    "British": "English", "American": "English", "Brazilian": "Portuguese",
    "Peruvian": "Spanish", "Other nationalities": "Other languages",
}

# e-Stat's prefecture codes, as both tables use them, with the census's name
# and the boundary file's.
PREFECTURES: dict[str, tuple[str, str]] = {
    "01000": ("北海道", "Hokkaido"), "02000": ("青森県", "Aomori"),
    "03000": ("岩手県", "Iwate"), "04000": ("宮城県", "Miyagi"),
    "05000": ("秋田県", "Akita"), "06000": ("山形県", "Yamagata"),
    "07000": ("福島県", "Fukushima"), "08000": ("茨城県", "Ibaraki"),
    "09000": ("栃木県", "Tochigi"), "10000": ("群馬県", "Gunma"),
    "11000": ("埼玉県", "Saitama"), "12000": ("千葉県", "Chiba"),
    "13000": ("東京都", "Tokyo"), "14000": ("神奈川県", "Kanagawa"),
    "15000": ("新潟県", "Niigata"), "16000": ("富山県", "Toyama"),
    "17000": ("石川県", "Ishikawa Prefecture"), "18000": ("福井県", "Fukui Prefecture"),
    "19000": ("山梨県", "Yamanashi"), "20000": ("長野県", "Nagano"),
    "21000": ("岐阜県", "Gifu Prefecture"), "22000": ("静岡県", "Shizuoka"),
    "23000": ("愛知県", "Aichi Prefecture"), "24000": ("三重県", "Mie Prefecture"),
    "25000": ("滋賀県", "Shiga"), "26000": ("京都府", "Kyoto Prefecture"),
    "27000": ("大阪府", "Osaka Prefecture"), "28000": ("兵庫県", "Hyogo Prefecture"),
    "29000": ("奈良県", "Nara Prefecture"), "30000": ("和歌山県", "Wakayama Prefecture"),
    "31000": ("鳥取県", "Tottori Prefecture"), "32000": ("島根県", "Shimane"),
    "33000": ("岡山県", "Okayama Prefecture"), "34000": ("広島県", "Hiroshima"),
    "35000": ("山口県", "Yamaguchi"), "36000": ("徳島県", "Tokushima Prefecture"),
    "37000": ("香川県", "Kagawa Prefecture"), "38000": ("愛媛県", "Ehime Prefecture"),
    "39000": ("高知県", "Kochi Prefecture"), "40000": ("福岡県", "Fukuoka Prefecture"),
    "41000": ("佐賀県", "Saga Prefecture"), "42000": ("長崎県", "Nagasaki Prefecture"),
    "43000": ("熊本県", "Kumamoto"), "44000": ("大分県", "Oita"),
    "45000": ("宮崎県", "Miyazaki Prefecture"), "46000": ("鹿児島県", "Kagoshima Prefecture"),
    "47000": ("沖縄県", "Okinawa Prefecture"),
}
NATIONAL = "00000"


# ---------------------------------------------------------------------------
# Arithmetic
# ---------------------------------------------------------------------------

def hundred(shares: dict[str, float]) -> list[dict[str, Any]]:
    """Shares to one decimal summing to exactly 100.0, largest remainder,
    largest first, name breaking a tie; a zero share is dropped."""
    total = sum(v for v in shares.values() if v > 0)
    if total <= 0:
        return []
    items = [(g, v / total * 1000) for g, v in shares.items() if v > 0]
    floors = [int(v) for _, v in items]
    order = sorted(range(len(items)), key=lambda i: -(items[i][1] - floors[i]))
    for i in order[:1000 - sum(floors)]:
        floors[i] += 1
    out = [{"group": g, "pct": floors[i] / 10} for i, (g, _) in enumerate(items)]
    out.sort(key=lambda r: (-r["pct"], r["group"]))
    return out


def tilt(prior: dict[str, float], none: float, national: dict[str, float],
         unit: dict[str, float], *, bound: float = TILT_BOUND,
         caps: dict[str, float] | None = None
         ) -> tuple[dict[str, float], dict[str, float], list[str]]:
    """The prior's affiliated part, tilted by a unit's signal relative to the nation's.

    ``prior`` is the survey's affiliated shares, ``none`` its no-religion
    share, ``national`` and ``unit`` are adherent counts by the same groups.
    Returns the tilted shares (affiliated groups plus "No religion", summing
    to ``sum(prior) + none``), the clipped ratios, and the groups a cap held.
    """
    caps = CAPS if caps is None else caps
    nat_total = sum(national[g] for g in prior)
    unit_total = sum(unit[g] for g in prior)
    if nat_total <= 0 or unit_total <= 0:
        raise ValueError("a signal with no adherents cannot tilt anything")
    ratios: dict[str, float] = {}
    for g in prior:
        nat_share = national[g] / nat_total
        unit_share = unit[g] / unit_total
        raw = (unit_share / nat_share) if nat_share > 0 else 1.0
        ratios[g] = min(max(raw, 1.0 / bound), bound)
    target = sum(prior.values())
    raw_shares = {g: prior[g] * ratios[g] for g in prior}
    scale = target / sum(raw_shares.values())
    shares = {g: v * scale for g, v in raw_shares.items()}
    # A capped group is held at its bound and the rest rescaled into what is
    # left, until nothing exceeds a bound. Two groups carry bounds, so this
    # runs at most twice.
    held: list[str] = []
    for _ in range(len(caps) + 1):
        over = [g for g in shares if g in caps and g not in held
                and shares[g] > caps[g] + 1e-9]
        if not over:
            break
        for g in over:
            shares[g] = caps[g]
            held.append(g)
        free = [g for g in shares if g not in held]
        remaining = target - sum(shares[g] for g in held)
        free_total = sum(shares[g] for g in free)
        for g in free:
            shares[g] = shares[g] / free_total * remaining if free_total > 0 else 0.0
    shares["No religion"] = none
    return shares, ratios, held


def distance(a: dict[str, float], b: dict[str, float]) -> float:
    """Total variation between two share dicts, in points."""
    keys = set(a) | set(b)
    return sum(abs(a.get(k, 0.0) - b.get(k, 0.0)) for k in keys) / 2


def languages_from(nationality: dict[str, float], *, floor: float = 0.0005
                   ) -> dict[str, float]:
    """Counts by nationality to counts by that nationality's majority language.

    A language under ``floor`` of the total (a twentieth of a point, which
    rounds to 0.0) is folded into "Other languages": an estimate that lists
    Thai at 0.0% is asserting a precision the assumption behind it does not
    have.
    """
    out: dict[str, float] = {}
    for group, count in nationality.items():
        if group not in LANGUAGE_OF:
            raise KeyError(f"no home language is declared for {group!r}")
        out[LANGUAGE_OF[group]] = out.get(LANGUAGE_OF[group], 0.0) + count
    total = sum(out.values())
    other = LANGUAGE_OF["Other nationalities"]
    for language in [g for g in out if g != other and out[g] < floor * total]:
        out[other] = out.get(other, 0.0) + out.pop(language)
    return out


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def imputation_caveat(nat: dict[str, int]) -> tuple[float, str]:
    """(points between the imputed and the recorded foreign share, the sentence
    that states the difference). ``nat`` is the table's 全国 row."""
    recorded = nat[CODE_FOREIGN] / (nat["2"] + nat[CODE_FOREIGN]) * 100
    imputed = PUBLISHED["foreign_imputed"] / PUBLISHED["total"] * 100
    to_foreign = PUBLISHED["foreign_imputed"] - nat[CODE_FOREIGN]
    sentence = (
        "The Bureau's 結果の概要 headline puts foreign nationals at "
        f"{PUBLISHED['foreign_imputed']:,} ({imputed:.1f}% of {PUBLISHED['total']:,}) against "
        f"the {nat[CODE_FOREIGN]:,} ({recorded:.1f}%) this table records, because the headline "
        f"is a 不詳補完値 that allocates the {nat[CODE_UNKNOWN]:,} people of unstated status, "
        f"{to_foreign:,} of them to foreign; shares here are of recorded nationalities only, "
        f"so the foreign share runs about {imputed - recorded:.1f} points low nationally.")
    return imputed - recorded, sentence


def check_nationality(table: dict[str, dict[str, int]]) -> str:
    """The census table against itself, then against the Bureau's printed figures.

    Refuses a table that is the wrong thing: prefectures that do not sum to
    its own 全国 row, nationalities that do not sum to its foreign total, a
    total that is not the census's, or a foreign share more than
    NATIONAL_TOLERANCE points from the one the Bureau's imputation prints.
    Returns the sentence that states the remaining difference.
    """
    nat = table[NATIONAL]
    for code, label in NATIONALITY_CODES.items():
        summed = sum(table[p][code] for p in PREFECTURES)
        if summed != nat[code]:
            raise SystemExit(f"japan: {label}: the 47 prefectures sum to {summed:,} against "
                             f"the table's own national {nat[code]:,}")
    foreign = sum(nat[c] for c in NATIONALITY_CODES if c != "2")
    if foreign != nat[CODE_FOREIGN]:
        raise SystemExit(f"japan: the thirteen nationalities sum to {foreign:,} against the "
                         f"table's foreign total {nat[CODE_FOREIGN]:,}")
    if nat[CODE_TOTAL] != nat["2"] + nat[CODE_FOREIGN] + nat[CODE_UNKNOWN]:
        raise SystemExit("japan: Japanese + foreign + unknown is not the table's total")
    if nat[CODE_TOTAL] != PUBLISHED["total"]:
        raise SystemExit(f"japan: the table's total {nat[CODE_TOTAL]:,} is not the census's "
                         f"published {PUBLISHED['total']:,}")
    if PUBLISHED["japanese_imputed"] + PUBLISHED["foreign_imputed"] != PUBLISHED["total"]:
        raise SystemExit("japan: the published imputed Japanese and foreign counts do not "
                         "sum to the published total")
    if nat[CODE_FOREIGN] > PUBLISHED["foreign_imputed"]:
        raise SystemExit(f"japan: the table records {nat[CODE_FOREIGN]:,} foreign nationals, "
                         f"more than the {PUBLISHED['foreign_imputed']:,} the imputation prints")
    points, sentence = imputation_caveat(nat)
    if abs(points) > NATIONAL_TOLERANCE:
        raise SystemExit(f"japan: the foreign share the Bureau's imputation prints is "
                         f"{points:.2f} points from this table's; not the same census")
    log(f"  nationality: the 47 prefectures reproduce the table's national row; total "
        f"{nat[CODE_TOTAL]:,} is the published one; the imputed foreign share is "
        f"{points:+.2f} points from the recorded one (stated on every prefecture)")
    return sentence


def check_believers(table: dict[str, dict[str, int]], population: dict[str, int]) -> None:
    """The signal is what the docstring says it is: memberships, not people."""
    nat = table[NATIONAL]
    for code in list(TRADITIONS) + [TRADITION_TOTAL]:
        summed = sum(table[p][code] for p in PREFECTURES)
        drift = abs(summed - nat[code]) / nat[code] if nat[code] else 0
        if drift > 0.001:
            raise SystemExit(f"japan: {TRADITIONS.get(code, 'total')} believers: prefectures "
                             f"sum to {summed:,} against a national {nat[code]:,}")
    for p in list(PREFECTURES) + [NATIONAL]:
        parts = sum(table[p][c] for c in TRADITIONS)
        if parts != table[p][TRADITION_TOTAL]:
            raise SystemExit(f"japan: {p}: the four traditions sum to {parts:,} against a "
                             f"total of {table[p][TRADITION_TOTAL]:,}")
    ratio = nat[TRADITION_TOTAL] / population[NATIONAL]
    if ratio < 1.0:
        raise SystemExit(f"japan: {nat[TRADITION_TOTAL]:,} believers against "
                         f"{population[NATIONAL]:,} people ({ratio:.2f} per person): this is "
                         "not the adherents table this module was written for")
    log(f"  believers: {nat[TRADITION_TOTAL]:,} against {population[NATIONAL]:,} people, "
        f"{ratio:.2f} per person; used as a relative signal only")


# ---------------------------------------------------------------------------
# e-Stat
# ---------------------------------------------------------------------------

def fetch_values(key: str, table: str, filters: dict[str, str], *, limit: int = 5000
                 ) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"statsDataId": table, "limit": limit,
                              "metaGetFlg": "N", "cntGetFlg": "N"}
    params.update(filters)
    payload = call("getStatsData", params, key)
    status, message, inner = result_of(payload, "GET_STATS_DATA")
    if status != 0:
        raise SystemExit(f"japan: e-Stat {table}: status {status}: {message}")
    data = inner.get("STATISTICAL_DATA") or {}
    info = data.get("RESULT_INF") or {}
    values = listed((data.get("DATA_INF") or {}).get("VALUE"))
    total = int(info.get("TOTAL_NUMBER", len(values)))
    if total > len(values):
        raise SystemExit(f"japan: e-Stat {table}: {total} values, {len(values)} on one page")
    log(f"  e-Stat {table}: {len(values)} values")
    return values


def fetch_nationality(key: str) -> dict[str, dict[str, int]]:
    """{area code: {国籍 code: persons}} for Japan and the 47 prefectures."""
    values = fetch_values(key, NATIONALITY_TABLE,
                          {"cdCat01": "0", "lvArea": "1-2", "cdTime": "2020000000"})
    out: dict[str, dict[str, int]] = {}
    for v in values:
        area = str(v.get("@area", ""))
        if area != NATIONAL and area not in PREFECTURES:
            continue
        try:
            out.setdefault(area, {})[str(v.get("@cat02"))] = int(str(v.get("$")))
        except ValueError:
            continue
    missing = [p for p in list(PREFECTURES) + [NATIONAL] if p not in out]
    if missing:
        raise SystemExit(f"japan: nationality table lacks areas {missing}")
    wanted = set(NATIONALITY_CODES) | {CODE_TOTAL, CODE_FOREIGN, CODE_UNKNOWN}
    for area, row in out.items():
        lacking = wanted - set(row)
        if lacking:
            raise SystemExit(f"japan: nationality table {area} lacks codes {sorted(lacking)}")
    return out


def fetch_believers(key: str) -> dict[str, dict[str, int]]:
    """{prefecture code: {宗教系統 code: believers}} at BELIEVERS_TIME."""
    values = fetch_values(key, BELIEVERS_TABLE,
                          {"cdCat02": "140", "cdCat03": "110", "cdTime": BELIEVERS_TIME})
    out: dict[str, dict[str, int]] = {}
    for v in values:
        area = str(v.get("@cat01", ""))
        try:
            out.setdefault(area, {})[str(v.get("@cat04"))] = int(str(v.get("$")))
        except ValueError:
            continue
    missing = [p for p in list(PREFECTURES) + [NATIONAL] if p not in out]
    if missing:
        raise SystemExit(f"japan: believers table lacks areas {missing}")
    wanted = set(TRADITIONS) | {TRADITION_TOTAL}
    for area, row in out.items():
        lacking = wanted - set(row)
        if lacking:
            raise SystemExit(f"japan: believers table {area} lacks codes {sorted(lacking)}")
    return out


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------

def prior_shares() -> tuple[dict[str, float], float]:
    """The survey prior with the no-answer 2% left out and the rest scaled to 100."""
    answered = sum(PRIOR.values()) + PRIOR_NONE
    scale = 100.0 / answered
    return {g: v * scale for g, v in PRIOR.items()}, PRIOR_NONE * scale


def religion_estimate(code: str, believers: dict[str, dict[str, int]]
                      ) -> tuple[dict[str, Any], float, list[str], dict[str, float]]:
    prior, none = prior_shares()
    national = {TRADITIONS[c]: float(believers[NATIONAL][c]) for c in TRADITIONS}
    unit = {TRADITIONS[c]: float(believers[code][c]) for c in TRADITIONS}
    shares, ratios, held = tilt(prior, none, national, unit)
    rows = hundred(shares)
    full_prior = dict(prior, **{"No religion": none})
    moved = distance(shares, full_prior)
    japanese, name = PREFECTURES[code]
    ratio_text = ", ".join(f"{g} x{ratios[g]:.2f}" for g in PRIOR)
    held_text = ("" if not held else
                 f"; {' and '.join(held)} came out above the bound and "
                 f"{'were' if len(held) > 1 else 'was'} held there, the rest rescaled")
    note = (
        "MODELLED, not read: no census or survey gives religion for this prefecture, and "
        "this is not evidence of what any census says. It is NHK's ISSP 2018 national "
        f"self-identification survey (Buddhism {PRIOR['Buddhism']:.0f}%, Shinto "
        f"{PRIOR['Shinto']:.0f}%, Christianity {PRIOR['Christianity']:.0f}%, other "
        f"{PRIOR['Other religions']:.0f}%, no religion {PRIOR_NONE:.0f}%, no answer "
        f"{PRIOR_NO_ANSWER:.0f}% left out) tilted by the Agency for Cultural Affairs' "
        f"宗教統計調査 believers by prefecture at {BELIEVERS_ASOF}, a membership count of "
        f"{believers[NATIONAL][TRADITION_TOTAL]:,} in a country of 126 million that is used "
        "only relatively: each tradition's share of this prefecture's "
        f"{believers[code][TRADITION_TOTAL]:,} reported believers over its share of the "
        f"nation's, clipped to 1/{TILT_BOUND:.0f}-{TILT_BOUND:.0f} ({ratio_text}), scales the "
        "survey's share, the four are rescaled to the survey's affiliated total, and no "
        "religion is held at the national figure because nothing gives it by prefecture. "
        f"Bounds: Christianity at most {CAPS['Christianity']:.0f}%, Shinto at most "
        f"{CAPS['Shinto']:.0f}%{held_text}. The result sits {moved:.1f} points from the prior; "
        "no backtest is possible, because no prefecture-level self-identification figure "
        f"exists. Written by the map owner's decision of {DECISION}.")
    est = estimate(MODELLED, rows, method=RELIGION_METHOD,
                   inputs=[f"nhk-issp-{PRIOR_YEAR}-japan",
                           f"estat-{BELIEVERS_TABLE}-{code}-{BELIEVERS_TIME}",
                           f"estat-{BELIEVERS_TABLE}-{NATIONAL}-{BELIEVERS_TIME}"],
                   note=note)
    est["tilt"] = {g: round(ratios[g], 3) for g in PRIOR}
    if held:
        est["capped"] = held
    return est, moved, held, shares


def nationality_composition(row: dict[str, int]) -> tuple[list[dict[str, Any]], int, int]:
    """(shares with counts, people with a known nationality, people without)."""
    counts = {label: row[code] for code, label in NATIONALITY_CODES.items()}
    known = sum(counts.values())
    rows = hundred({g: float(c) for g, c in counts.items()})
    for r in rows:
        r["count"] = counts[r["group"]]
    return rows, known, row[CODE_UNKNOWN]


def language_estimate(code: str, row: dict[str, int], ethnicity_id: str) -> dict[str, Any]:
    counts = {label: float(row[c]) for c, label in NATIONALITY_CODES.items()}
    by_language = languages_from(counts)
    rows = hundred(by_language)
    japanese_share = by_language["Japanese"] / sum(by_language.values()) * 100
    note = (
        "MODELLED, not read: Japan's census does not ask language, and this is not evidence "
        "of what any census says. It is this prefecture's 2020 census nationality "
        "composition with everyone assigned their nationality's majority home language "
        "(Chinese to Mandarin, Filipino to Filipino, Brazilian to Portuguese, Peruvian to "
        "Spanish, Indian to Hindi, a plurality not a majority, British and American to "
        f"English), so Japanese at {japanese_share:.1f}% is simply the share holding Japanese "
        "nationality. That understates Japanese-speaking among Japan-born Koreans and "
        "Brazilians of Japanese descent, overstates it among naturalised citizens' "
        "families, and says nothing of Ainu or Ryukyuan; no backtest is possible, because "
        f"no prefecture-level language figure exists. Written by the map owner's decision "
        f"of {DECISION}.")
    return estimate(MODELLED, rows, method=LANGUAGE_METHOD,
                    inputs=[ethnicity_id, f"estat-{NATIONALITY_TABLE}-{code}"], note=note)


def build(nationality: dict[str, dict[str, int]], believers: dict[str, dict[str, int]]
          ) -> list[dict[str, Any]]:
    caveat = check_nationality(nationality)
    population = {p: nationality[p][CODE_TOTAL] for p in nationality}
    check_believers(believers, population)
    prior, none = prior_shares()
    log(f"  prior (no answer left out): no religion {none:.1f}, "
        + ", ".join(f"{g} {v:.1f}" for g, v in prior.items()))
    sources = [
        {"field": "ethnicity/population", "name": NATIONALITY_SOURCE,
         "url": NATIONALITY_URL, "year": CENSUS_YEAR, "license": ESTAT_LICENCE},
        {"field": "religion", "name": PRIOR_SOURCE, "url": PRIOR_URL, "year": PRIOR_YEAR,
         "license": "(c) NHK; five printed percentages cited for research"},
        {"field": "religion", "name": BELIEVERS_SOURCE, "url": BELIEVERS_URL,
         "year": 2024, "license": ESTAT_LICENCE},
        {"field": "language", "name": NATIONALITY_SOURCE + ", each nationality assigned "
         "its majority home language", "url": NATIONALITY_URL, "year": CENSUS_YEAR,
         "license": ESTAT_LICENCE},
    ]
    records = []
    moved: list[tuple[float, str, list[str], dict[str, float]]] = []
    for code, (japanese, name) in PREFECTURES.items():
        row = nationality[code]
        shares, known, unknown = nationality_composition(row)
        total = sum(r["pct"] for r in shares)
        if abs(total - 100.0) > SUM_TOLERANCE:
            raise SystemExit(f"japan: {name}: nationality shares sum to {total}")
        entity_id = f"JPN-{slugify(name)}"
        religion, dist, held, tilted = religion_estimate(code, believers)
        moved.append((dist, name, held, tilted))
        ethnicity_note = (
            f"2020 Population Census (e-Stat table {NATIONALITY_TABLE}): population by "
            "NATIONALITY, not ethnicity, which Japan's census does not ask. 'Japanese' is "
            "everyone holding Japanese nationality, naturalised citizens and people of any "
            "ancestry included (Ainu, Ryukyuans and naturalised Japan-born Koreans among "
            "them); 'Korean' is the census's 韓国，朝鮮 row. Shares are of the "
            f"{known:,} people whose nationality the census recorded; {unknown:,} "
            f"({unknown / row[CODE_TOTAL] * 100:.1f}% of {row[CODE_TOTAL]:,}) recorded as "
            f"neither Japanese nor foreign are left out. {caveat} Written by the map owner's "
            f"decision of {DECISION}.")
        records.append(record(
            entity_id, name, level="admin1", parent="JPN", country="JPN",
            sources=sources,
            population=measure(row[CODE_TOTAL], year=CENSUS_YEAR, source=NATIONALITY_SOURCE),
            ethnicity=shares, ethnicity_year=CENSUS_YEAR, ethnicity_basis="nationality",
            ethnicity_note=ethnicity_note,
            religion=religion,
            language=language_estimate(code, row, entity_id),
        ))
    moved.sort(key=lambda m: -m[0])
    log("  religion: the five prefectures the tilt moves furthest from the national prior:")
    for dist, name, held, tilted in moved[:5]:
        top = ", ".join(f"{g} {tilted[g]:.1f}" for g in ("Buddhism", "Shinto", "Christianity",
                                                        "Other religions"))
        log(f"      {name:22} {dist:5.1f} points  {top}"
            + (f"  (held at the bound: {', '.join(held)})" if held else ""))
    capped = [name for _, name, held, _ in moved if held]
    log(f"  religion: {len(capped)} prefecture{'' if len(capped) == 1 else 's'} hit a bound"
        + (f": {', '.join(capped)}" if capped else ""))
    return records


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.parse_args()
    log(f"japan: nationality from e-Stat {NATIONALITY_TABLE}, believers from "
        f"{BELIEVERS_TABLE}, prior from NHK/ISSP {PRIOR_YEAR}")
    key = app_id()
    nationality = fetch_nationality(key)
    believers = fetch_believers(key)
    records = build(nationality, believers)
    if len(records) != 47:
        raise SystemExit(f"japan: expected 47 prefectures, built {len(records)}")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    sys.exit(main())
