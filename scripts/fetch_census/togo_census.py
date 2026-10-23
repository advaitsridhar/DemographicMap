#!/usr/bin/env python3
"""Togo -- the fifth census (RGPH-5, November 2022) by region and prefecture.

INSEED's leaflet of the definitive results (*Résultats définitifs du RGPH-5 de
Novembre 2022*, April 2023) prints the population of every prefecture, region
and the country by sex: 39 prefectures, Grand Lomé apart from the rest of the
Maritime region, 8,095,498 people.

**The ground the map draws.** The boundary file draws the five regions, the
Maritime region with Grand Lomé in it, and 37 prefectures on their lines from
before the reforms of 2017-2019:

* Kpendjal-Ouest was made from Kpendjal and Oti-Sud from Oti, so the polygons
  of Kpendjal and Oti take the two prefectures each now is, added.
* Grand Lomé is counted as the prefectures of Golfe and Agoè-Nyivé, made out of
  the commune of Lomé and the earlier prefecture of Golfe; the map draws those
  two older units. No 2022 count is either polygon's own, so neither is
  written here and each keeps what other sources give it.
* Mô is drawn as "Plaine de Mô", the prefecture's earlier name.

Written for every region and every other prefecture: population and sex
ratio (men per 1,000 women), 2022, the census replacing OCHA's 2021
projection.

**Checks before anything is written.** Every row's men and women make its
total; each region's prefectures make the region; the regions make the
country's 8,095,498.

Usage:
    python -m scripts.fetch_census.togo_census
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

from ._shared import PROCESSED, log, measure, record, write_json

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from probe_pdf import fetch_blob, laid_out  # noqa: E402

URL = "https://inseed.tg/wp-content/uploads/2023/09/Depliant-Resultats-Definitifs_RGPH5_02Avril2023.pdf"
PAGE = "https://inseed.tg/depliant-et-communique-rgph/"
SOURCE = ("Institut National de la Statistique et des Etudes Economiques et Démographiques "
          "(INSEED) du Togo, Cinquième Recensement Général de la Population et de l'Habitat "
          "(RGPH-5) de novembre 2022, Résultats définitifs (dépliant, avril 2023)")
LICENCE = "INSEED publication (reuse with attribution)"
YEAR = 2022
NATIONAL = (3_944_510, 4_150_988, 8_095_498)
OUT = "togo_census.json"
SITE = PROCESSED.parent.parent / "site" / "data"

# The leaflet's regions and their prefectures, as printed.
REGIONS = {
    "Grand Lomé": ["Golfe", "Agoè-Nyivé"],
    "Maritime sans Grand Lomé": ["Zio", "Yoto", "Bas-Mono", "Lacs", "Vo", "Avé"],
    "Plateaux": ["Ogou", "Moyen-Mono", "Haho", "Agou", "Kloto", "Kpélé", "Danyi", "Wawa",
                 "Akébou", "Amou", "Anié", "Est-Mono"],
    "Centrale": ["Tchaoudjo", "Tchamba", "Blitta", "Sotouboua", "Mô"],
    "Kara": ["Kozah", "Assoli", "Bassar", "Dankpen", "Kéran", "Doufelgou", "Binah"],
    "Savanes": ["Tône", "Cinkassé", "Kpendjal-Ouest", "Kpendjal", "Oti-Sud", "Oti", "Tandjoaré"],
}
# The boundary file's first-level polygons (folded) -> the leaflet's regions.
POLYGONS = {"maritimeregion": ["Grand Lomé", "Maritime sans Grand Lomé"],
            "plateauxregion": ["Plateaux"], "centraleregion": ["Centrale"],
            "kararegion": ["Kara"], "savanesregion": ["Savanes"]}
# Second-level polygons (folded) -> the prefectures on their ground.
JOINED = {"kpendjal": ["Kpendjal", "Kpendjal-Ouest"], "oti": ["Oti", "Oti-Sud"],
          "plainedemo": ["Mô"], "tandjouare": ["Tandjoaré"]}
# Polygons drawn on lines no 2022 prefecture follows.
NOT_THIS_GROUND = {"golfe", "lomecommune"}


def fold(text: Any) -> str:
    s = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(c for c in s.lower() if c.isalpha() and not unicodedata.combining(c))


def grouped(chunk: list[str]) -> bool:
    return (bool(chunk) and all(t.isdigit() for t in chunk) and 1 <= len(chunk[0]) <= 3
            and all(len(t) == 3 for t in chunk[1:]))


def first_triple(tokens: list[str]) -> tuple[int, int, int] | None:
    """(men, women, total): the first run of the tokens that reads as three
    numbers, the first two making the third. A leaflet line can carry text of
    the column beside it after the figures ("164 460 8 095 498")."""
    digits = [t for t in tokens if t.isdigit()]
    n = len(digits)
    for a in range(1, min(n, 3) + 1):
        if not grouped(digits[:a]):
            continue
        for b in range(a + 1, min(n, a + 3) + 1):
            if not grouped(digits[a:b]):
                continue
            for c in range(b + 1, min(n, b + 3) + 1):
                if not grouped(digits[b:c]):
                    continue
                men, women, total = (int("".join(digits[i:j])) for i, j in
                                     ((0, a), (a, b), (b, c)))
                if men + women == total:
                    return men, women, total
    return None


def parse(text: str) -> dict[str, tuple[int, int, int]]:
    """{name: (men, women, total)} for every prefecture, region and the country
    the leaflet prints on one line with its name."""
    wanted = {fold(n): n for n in list(REGIONS) + [p for ps in REGIONS.values() for p in ps]
              + ["Togo"]}
    out: dict[str, tuple[int, int, int]] = {}
    for line in text.splitlines():
        m = re.match(r"^\s*([^\d]+?)\s+(\d[\d ]*\d)(?:\s|$)", line)
        if not m:
            continue
        name = wanted.get(fold(m.group(1)))
        if name is None or name in out:
            continue
        figures = first_triple(line[m.start(2):].split())
        if figures:
            out[name] = figures
    return out


def check(table: dict[str, tuple[int, int, int]]) -> dict[str, tuple[int, int, int]]:
    """Every region's figures, the two-line one made from its prefectures; and
    the checks the leaflet's own totals allow."""
    missing = [p for ps in REGIONS.values() for p in ps if p not in table]
    if missing or "Togo" not in table:
        raise SystemExit(f"togo_census: the leaflet lacks {missing or ['Togo']}")
    if table["Togo"] != NATIONAL:
        raise SystemExit(f"togo_census: the country's line reads {table['Togo']}")
    regions = {}
    for region, prefectures in REGIONS.items():
        made = tuple(sum(table[p][i] for p in prefectures) for i in range(3))
        printed = table.get(region)
        if printed is not None and printed != made:
            raise SystemExit(f"togo_census: {region}'s prefectures make {made}, not {printed}")
        regions[region] = made
    made = tuple(sum(v[i] for v in regions.values()) for i in range(3))
    if made != NATIONAL:
        raise SystemExit(f"togo_census: the regions make {made}, not {NATIONAL}")
    return regions


def fields(men: int, women: int, total: int, note: str) -> dict[str, Any]:
    return {"population": measure(total, year=YEAR, source=SOURCE),
            "population_note": note,
            "sex_ratio": measure(round(1000 * men / women), unit="males_per_1000_females",
                                 year=YEAR, source=SOURCE),
            "sources": [{"field": "population/sex_ratio", "name": SOURCE, "url": URL,
                         "page": PAGE, "license": LICENCE, "year": YEAR}]}


def build(text: str, admin1: list[dict[str, Any]],
          admin2: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    table = parse(text)
    regions = check(table)
    records: list[dict[str, Any]] = []
    report: list[str] = []
    prefectures_of: dict[str, list[str]] = {}
    for shape in admin1:
        parts = POLYGONS.get(fold(shape["name"]))
        if not parts:
            report.append(f"region polygon {shape['name']!r}: no census region")
            continue
        prefectures_of[shape["id"]] = [p for r in parts for p in REGIONS[r]]
        men, women, total = (sum(regions[r][i] for r in parts) for i in range(3))
        name = shape["name"].replace(" Region", "")
        note = (f"The 2022 census's count for the {name} region, Grand Lomé ({regions['Grand Lomé'][2]:,}) "
                "included." if len(parts) > 1 else
                f"The 2022 census's count for the {name} region.")
        records.append(record(f"TGO-RGPH5-region-{fold(name)}", shape["name"], level="admin1",
                              parent="TGO", country="TGO", match_by="shape_id",
                              shape_id=shape["id"], **fields(men, women, total, note)))
    used: set[str] = set()
    for shape in admin2:
        key = fold(shape["name"])
        if key in NOT_THIS_GROUND:
            report.append(f"{shape['name']!r}: drawn on lines no 2022 prefecture follows")
            continue
        within = prefectures_of.get(shape.get("parent"), [])
        names = JOINED.get(key) or [p for p in within if fold(p) == key]
        if not names or any(n not in within or n in used for n in names):
            report.append(f"prefecture polygon {shape['name']!r}: not bound")
            continue
        used.update(names)
        men, women, total = (sum(table[n][i] for n in names) for i in range(3))
        if len(names) > 1:
            note = (f"Drawn on its outline from before {names[1]} prefecture was made from it; "
                    f"the 2022 census counts the two apart, {names[0]} {table[names[0]][2]:,} "
                    f"and {names[1]} {table[names[1]][2]:,}, added here.")
        elif names[0] == "Mô":
            note = "The 2022 census's count for the prefecture of Mô, drawn as Plaine de Mô."
        else:
            note = f"The 2022 census's count for the prefecture of {names[0]}."
        records.append(record(f"TGO-RGPH5-{fold(names[0])}", shape["name"], level="admin2",
                              parent="TGO", country="TGO", match_by="shape_id",
                              shape_id=shape["id"], **fields(men, women, total, note)))
    left = sorted(p for ps in REGIONS.values() for p in ps
                  if p not in used and p not in REGIONS["Grand Lomé"])
    if left:
        report.append(f"prefectures not bound: {left}")
    return records, report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", default="", help="a label that tells one dispatch from another")
    ap.parse_args()
    blob = fetch_blob(URL)
    if not blob.startswith(b"%PDF"):
        raise SystemExit(f"togo_census: {URL} is not a PDF: {blob[:60]!r}")
    log(f"  read {URL}: {len(blob):,} bytes, sha256 {hashlib.sha256(blob).hexdigest()}")
    text = laid_out(blob)
    admin1 = json.loads((SITE / "admin1" / "TGO.units.json").read_text())
    admin2 = json.loads((SITE / "admin2" / "TGO.units.json").read_text())
    records, report = build(text, admin1, admin2)
    for line in report:
        log("  " + line)
    for r in records:
        log(f"  {r['level']} {r['name']}: {r['population']['value']:,}, "
            f"{r['sex_ratio']['value']} men per 1,000 women")
    n1 = sum(1 for r in records if r["level"] == "admin1")
    n2 = sum(1 for r in records if r["level"] == "admin2")
    log(f"  {n1} regions and {n2} prefectures bound")
    if n1 != 5 or n2 != 35:
        raise SystemExit(f"togo_census: expected 5 regions and 35 prefectures, bound {n1} and {n2}")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
