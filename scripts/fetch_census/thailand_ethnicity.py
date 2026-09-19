#!/usr/bin/env python3
"""Thailand: ethnicity by province, modelled from what the census counted.

Thailand's census does not ask ethnicity, and for as long as this map read
only counts the 77 provinces said so. On 19 September 2026 the map's owner
decided that Thailand's provinces should carry what secondary sources can
say, the way Japan's prefectures do, provided every figure is labelled for
what it is: a real count as a composition, anything estimated as a
``modelled`` estimate with its method on the record. This module is that
decision for ethnicity, and everything it writes is an estimate.

**What was looked for first, and what was found.** The standard secondary
source is the *Ethnolinguistic Maps of Thailand* (Suwilai Premsrirat et al.,
Mahidol University Institute of Language and Culture, 2004), which names the
ethnolinguistic groups of every province and estimates their populations.
Its tables are not reachable by a clean client: the Sirindhorn
Anthropology Centre's ethnic-groups database (``ethnicity.sac.or.th``)
answers 403, the institute's own host serves a certificate for another name,
and ``langrevival.mahidol.ac.th`` answers 403. What is reachable is the
national table the maps yield, transcribed in the Wikipedia article
*Demographics of Thailand* (``NATIONAL``), which has no province in it.
Kaggle's catalogue was searched for Thailand census, population, language
and ethnicity datasets and holds none. So no per-province ethnolinguistic
table exists where this project can read one, and the province figure has
to be a model.

**What the model is.** Two inputs and one assumption:

1. The 2000 Population and Housing Census asked the language spoken at
   home, and each provincial final report tabulates the minorities: the
   Wikipedia article *Nationality, religion, and language data for the
   provinces of Thailand* -- the one ``thailand.py`` already reads for
   religion -- transcribes that cell for every province ("Khmer (47.2%)",
   "Malay (66.1%), Chinese (3.0%)", "Hill tribe languages (63.0%)"). Those
   shares are read as printed, under the census's own category names.
2. Everyone else in the province -- counted by the census as speaking Thai,
   with the few it filed as other -- is assigned to the regional Tai group
   the Ethnolinguistic Maps give for the province's region: Northern Thai
   (Kam Mueang) in the eight upper-northern provinces, Isan (Lao) in the
   twenty of the northeast, Southern Thai (Pak Tai) in the fourteen of the
   south, Central Thai everywhere else. That assignment is the model.

It is wrong in ways that are known and printed on every record. The census
counted Isan, Northern and Southern Thai as "Thai", so their shares here are
a region's remainder and not a count; the Tai groups the maps count apart
(Thai Khorat, Phu Thai, Nyaw, Kaleung, Phuan, Lue, Shan) and the
Austroasiatic ones the census did not name (Kuy, So, Bru, Mon) are inside
that remainder; and the Thai Chinese, a tenth or more of the population by
descent, are a few hundred thousand by home language and otherwise counted
as Thai. A minority the report printed below 0.1% is named in the note and
not carried as a share.

**The check.** The national composition the 76 modelled provinces imply,
weighted by population, is printed beside the maps' national figures read
against the 2000 census population. Measured on the first run: it agrees
where the census counted (Khmer 2.3% against the maps' 2.3, Malay 2.7
against 2.3) and disagrees where the model assigns -- Central Thai 43.6%
against 32.8, Isan 30.1 against 25.0, Southern Thai 11.7 against 7.4,
Northern Thai 7.9 against 9.8. The maps' ten largest groups account for
82.6% of the 2000 population and the model's regional remainders for all of
it, so the remainders run high, and by most where the Thai Chinese and the
smaller Tai groups live; that is the assumption showing, and it is the
reason the figure is an estimate. The population weights are the December
2024 figures the article *Provinces of Thailand* carries -- the 2000
provincial totals sit behind the same hosts as everything else the NSO
publishes.

**Bueng Kan** was carved out of Nong Khai in 2011 and has no 2000 row, so it
stays empty, as it does for religion.

Usage:
    python -m scripts.fetch_census.thailand_ethnicity
    python -m scripts.fetch_census.thailand_ethnicity --wikitext saved.txt \\
        --provinces-wikitext provinces.txt                       # offline
"""

from __future__ import annotations

import argparse
import re
import sys
import urllib.parse
from pathlib import Path
from typing import Any

from ._shared import PROCESSED, http_json, log, record, write_json
from .thailand import ALIASES, API, HEADER, LICENCE, PAGE, SOURCE, plain, province, table

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import MODELLED, estimate  # noqa: E402
from probe_wikitable import tables  # noqa: E402

OUT = "thailand_ethnicity.json"
YEAR = 2000
DECISION = "19 September 2026"
METHOD = "tier1-census-home-language-plus-regional-assignment"
EXPECTED = 76                                     # 77 provinces less Bueng Kan
COLUMN = HEADER.index("Linguistic minorities in 2000")
SUM_TOLERANCE = 0.3

MAPS = ("Suwilai Premsrirat et al., Ethnolinguistic Maps of Thailand (Mahidol University "
        "Institute of Language and Culture / Office of the National Culture Commission, 2004)")
MAPS_YEAR = 2004
NATIONAL_PAGE = "Demographics of Thailand"
NATIONAL_URL = "https://en.wikipedia.org/wiki/" + NATIONAL_PAGE.replace(" ", "_")
# The maps' national figures as that article transcribes them (persons),
# and the 2000 census population they are read against.
NATIONAL: dict[str, float] = {
    "Central Thai": 20_000_000, "Isan (Lao)": 15_200_000, "Northern Thai": 6_000_000,
    "Southern Thai": 4_500_000, "Khmer": 1_400_000, "Malay": 1_400_000,
    "Nyaw": 500_000, "Phu Thai": 500_000, "Karen": 400_000, "Kuy": 400_000,
}
CENSUS_POPULATION = 60_916_441                     # 2000 Population and Housing Census

PROVINCES_PAGE = "Provinces of Thailand"
PROVINCES_API = ("https://en.wikipedia.org/w/api.php?action=parse&prop=wikitext&format=json"
                 "&formatversion=2&redirects=1&page=" + PROVINCES_PAGE.replace(" ", "_"))

# The census's wording for a minority -> the label the map carries. A wording
# not here refuses the run: it would be a category this was never read for.
CATEGORIES: dict[str, str] = {
    "Khmer": "Khmer",
    "Malay": "Malay",
    "Malay-Yawi": "Malay",
    "Chinese": "Chinese",
    "Hill tribe languages": "Hill tribe languages (census category)",
    "Burmese and Peguan": "Burmese and Mon",
    "Laotian and Vietnamese": "Lao and Vietnamese",
    "English": "English",
    "Indian languages": "Indian",
    "Japanese": "Japanese",
}

# The regional Tai group of every province, by the article's bare spelling
# (the link target less the word "province"). Four sets, disjoint, 77 names.
NORTHERN = frozenset({
    "Chiang Mai", "Chiang Rai", "Lampang", "Lamphun", "Mae Hong Son", "Nan",
    "Phayao", "Phrae",
})
NORTHEASTERN = frozenset({
    "Amnat Charoen", "Bueng Kan", "Buriram", "Chaiyaphum", "Kalasin", "Khon Kaen",
    "Loei", "Maha Sarakham", "Mukdahan", "Nakhon Phanom", "Nakhon Ratchasima",
    "Nong Bua Lam Phu", "Nong Khai", "Roi Et", "Sakon Nakhon", "Sisaket", "Surin",
    "Ubon Ratchathani", "Udon Thani", "Yasothon",
})
SOUTHERN = frozenset({
    "Chumphon", "Krabi", "Nakhon Si Thammarat", "Narathiwat", "Pattani", "Phangnga",
    "Phatthalung", "Phuket", "Ranong", "Satun", "Songkhla", "Surat Thani", "Trang",
    "Yala",
})
CENTRAL = frozenset({
    "Bangkok", "Ang Thong", "Chachoengsao", "Chai Nat", "Chanthaburi", "Chonburi",
    "Kamphaeng Phet", "Kanchanaburi", "Lopburi", "Nakhon Nayok", "Nakhon Pathom",
    "Nakhon Sawan", "Nonthaburi", "Pathum Thani", "Phetchabun", "Phetchaburi",
    "Phichit", "Phitsanulok", "Phra Nakhon Si Ayutthaya", "Prachin Buri",
    "Prachuap Khiri Khan", "Ratchaburi", "Rayong", "Sa Kaeo", "Samut Sakhon",
    "Samut Songkhram", "Samutprakan", "Saraburi", "Sing Buri", "Sukhothai",
    "Suphan Buri", "Tak", "Trat", "Uthai Thani", "Uttaradit",
})
REGION: dict[str, str] = {}
for _group, _names in (("Northern Thai", NORTHERN), ("Isan (Lao)", NORTHEASTERN),
                       ("Southern Thai", SOUTHERN), ("Central Thai", CENTRAL)):
    REGION.update({name: _group for name in _names})

MINORITY = re.compile(r"([A-Za-z][A-Za-z\- ]*?)\s*\(\s*(<)?\s*(\d+(?:\.\d+)?)\s*\)")


def minorities(cell: str) -> tuple[dict[str, float], list[str]]:
    """The cell's named minorities -> (label: share at or above 0.1%,
    the labels printed below it)."""
    text = plain(cell)
    if text.upper() in ("N/A", "NA", "", "-"):
        return {}, []
    found = MINORITY.findall(text)
    if not found:
        raise SystemExit(f"thailand_ethnicity: cannot read {cell!r} as minorities")
    shares: dict[str, float] = {}
    below: list[str] = []
    for wording, less, value in found:
        wording = wording.strip()
        if wording not in CATEGORIES:
            raise SystemExit(f"thailand_ethnicity: the census names {wording!r}, "
                             "a category this was never read for")
        label = CATEGORIES[wording]
        pct = round(float(value), 1)
        if less or pct < 0.1:
            below.append(label)
            continue
        shares[label] = shares.get(label, 0.0) + pct
    return shares, below


def note_for(name: str, group: str, shares: dict[str, float], rest: float,
             below: list[str]) -> str:
    counted = (", ".join(f"{g} {p:.1f}%" for g, p in sorted(shares.items(), key=lambda kv: -kv[1]))
               or "no minority at or above 0.1%")
    unnamed = (f"; {', '.join(below)} printed below 0.1% and not carried" if below else "")
    # One sentence saying what the figure is, then the caveats, short. The
    # method in full is in docs/SOURCES.md and docs/MODELLING.md; a paragraph
    # repeated 76 times was, in the owner's words, "so annoying".
    return (
        f"Modelled from the 2000 census's language-spoken-at-home table for {name} "
        f"({counted}{unnamed}) with the remaining {rest:.1f}%, whom the census counted as "
        f"Thai speakers, assigned to the regional Tai group the Ethnolinguistic Maps of "
        f"Thailand ({MAPS_YEAR}) give for this region: {group}. Thailand's census does not "
        "ask ethnicity, so this is a model, not a count: the regional share cannot "
        "separate the Tai groups the maps count apart, and the Thai Chinese, a tenth or "
        "more of the population by descent, are counted as Thai. Transcribed by the "
        f"Wikipedia article '{PAGE}'; owner's decision of {DECISION}; a census or survey "
        "figure replaces it when one is read.")


def build(wikitext: str) -> list[dict[str, Any]]:
    rows = table(wikitext)
    header = [plain(c) for c in rows[0]]
    if header != HEADER:
        raise SystemExit(f"thailand_ethnicity: the table's columns changed: {header}")
    records: list[dict[str, Any]] = []
    for cells in rows[1:]:
        if len(cells) != len(HEADER):
            raise SystemExit(f"thailand_ethnicity: row has {len(cells)} cells: "
                             f"{cells[0][:60]!r}")
        bare, report = province(cells[0])
        group = REGION.get(bare)
        if group is None:
            raise SystemExit(f"thailand_ethnicity: {bare!r} is in no region; the article "
                             "renamed a province")
        shares, below = minorities(cells[COLUMN])
        summed = round(sum(shares.values()), 1)
        if summed > 100.0:
            raise SystemExit(f"thailand_ethnicity: {bare}: minorities add to {summed}%")
        rest = round(100.0 - summed, 1)
        minor = dict(shares)
        shares[group] = shares.get(group, 0.0) + rest
        bars = [{"group": g, "pct": p} for g, p in
                sorted(shares.items(), key=lambda kv: (-kv[1], kv[0]))]
        total = sum(r["pct"] for r in bars)
        if abs(total - 100.0) > SUM_TOLERANCE:
            raise SystemExit(f"thailand_ethnicity: {bare}: shares sum to {total}")
        name = bare if bare == "Bangkok" else f"{bare} Province"
        aliases = ALIASES.get(bare, [])
        if bare != "Bangkok" and bare not in aliases:
            aliases = aliases + [bare]
        entity_id = f"THA-{bare.replace(' ', '_')}"
        est = estimate(
            MODELLED, bars, method=METHOD,
            inputs=[f"nso-{YEAR}-census-{bare.replace(' ', '-').lower()}-home-language",
                    f"ethnolinguistic-maps-of-thailand-{MAPS_YEAR}-regional-groups"],
            note=note_for(name, group, minor, rest, below))
        est["census_year"] = YEAR
        est["regional_group"] = group
        records.append(record(
            entity_id, name, level="admin1", parent="THA", country="THA", aliases=aliases,
            ethnicity=est,
            sources=[
                {"field": "ethnicity", "name": f"{SOURCE}, language spoken at home",
                 "url": report or API, "year": YEAR, "license": LICENCE},
                {"field": "ethnicity", "name": f"{MAPS}, regional groups and national "
                 f"figures as transcribed in the Wikipedia article '{NATIONAL_PAGE}'",
                 "url": NATIONAL_URL, "year": MAPS_YEAR, "license": "compilation CC BY-SA 4.0"},
            ],
        ))
    return records


def key(name: str) -> str:
    """'Phang Nga' and 'Phangnga', 'Si Sa Ket' and 'Sisaket': one key."""
    return re.sub(r"[^a-z]", "", name.lower())


def populations(wikitext: str) -> dict[str, int]:
    """Province -> population, from the article's main table, by matching key."""
    for t in tables(wikitext):
        if not t:
            continue
        head = [c.lower() for c in t[0]]
        name_col = next((i for i, c in enumerate(head) if c == "name"), None)
        pop_col = next((i for i, c in enumerate(head) if c.startswith("population")), None)
        if name_col is None or pop_col is None:
            continue
        out: dict[str, int] = {}
        for row in t[1:]:
            if len(row) <= max(name_col, pop_col):
                continue
            name = re.sub(r"\s*\(.*\)\s*$", "", row[name_col]).strip()
            digits = re.sub(r"[^\d]", "", row[pop_col])
            if name and digits:
                out[key(name)] = int(digits)
        if len(out) >= 70:
            return out
    raise SystemExit(f"thailand_ethnicity: no province population table in '{PROVINCES_PAGE}'")


def national(records: list[dict[str, Any]], weights: dict[str, int]) -> dict[str, float]:
    """The national composition the provinces imply, weighted by population."""
    total = 0
    persons: dict[str, float] = {}
    for rec in records:
        bare = rec["id"][len("THA-"):].replace("_", " ")
        pop = weights.get(key(bare))
        if pop is None:
            raise SystemExit(f"thailand_ethnicity: no population for {bare!r}")
        total += pop
        for row in rec["ethnicity"]["estimate"]:
            persons[row["group"]] = persons.get(row["group"], 0.0) + row["pct"] * pop / 100
    return {g: round(100 * v / total, 1) for g, v in persons.items()}


def compare(records: list[dict[str, Any]], weights: dict[str, int]) -> dict[str, float]:
    shares = national(records, weights)
    log(f"  national composition the {len(records)} provinces imply, weighted by the "
        f"December 2024 populations, beside the Ethnolinguistic Maps' national figures "
        f"({MAPS_YEAR}) read against the {YEAR} census population of {CENSUS_POPULATION:,}:")
    log(f"      {'group':40} {'modelled':>9} {'maps':>9}")
    seen = set()
    for group, pct in sorted(shares.items(), key=lambda kv: -kv[1]):
        seen.add(group)
        ref = NATIONAL.get(group)
        ref_text = f"{100 * ref / CENSUS_POPULATION:8.1f}%" if ref else "        -"
        log(f"      {group:40} {pct:8.1f}% {ref_text}")
    for group, ref in NATIONAL.items():
        if group not in seen:
            log(f"      {group:40} {'-':>9} {100 * ref / CENSUS_POPULATION:8.1f}%   "
                "(inside a regional remainder here)")
    return shares


def fetch(url: str, title: str) -> str:
    parsed = http_json(url, timeout=90).get("parse") or {}
    text = parsed.get("wikitext") or ""
    log(f"  {title!r}: {len(text):,} bytes of wikitext")
    return text


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=None)
    ap.add_argument("--wikitext", default=None,
                    help="a saved copy of the provincial data article's wikitext")
    ap.add_argument("--provinces-wikitext", default=None,
                    help="a saved copy of the 'Provinces of Thailand' wikitext")
    args = ap.parse_args()

    log(f"thailand_ethnicity: modelled from {SOURCE} (home language) and the {MAPS_YEAR} "
        f"Ethnolinguistic Maps' regional groups, by the owner's decision of {DECISION}")
    wikitext = (Path(args.wikitext).read_text(encoding="utf-8") if args.wikitext
                else fetch(API, PAGE))
    records = build(wikitext)
    log(f"  {len(records)} provinces modelled")
    if len(records) != EXPECTED:
        raise SystemExit(f"thailand_ethnicity: expected {EXPECTED} provinces, "
                         f"built {len(records)}")
    by_group: dict[str, int] = {}
    for rec in records:
        by_group[rec["ethnicity"]["regional_group"]] = \
            by_group.get(rec["ethnicity"]["regional_group"], 0) + 1
    log("  regional groups: " + ", ".join(f"{g} {n}" for g, n in sorted(by_group.items())))
    provinces = (Path(args.provinces_wikitext).read_text(encoding="utf-8")
                 if args.provinces_wikitext else fetch(PROVINCES_API, PROVINCES_PAGE))
    compare(records, populations(provinces))
    write_json(Path(args.out) if args.out else PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
