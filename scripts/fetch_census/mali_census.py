#!/usr/bin/env python3
"""Mali -- population, sex ratio and median age: the 2022 census by region,
the 2009 census by cercle.

**The regions.** INSTAT's report on the state and structure of the population
of the fifth census (*Rapport d'analyse ... État et structure de la
population*, RGPH5, December 2024) tabulates the 19 regions and the District
of Bamako of the 2023 reform: everyone by sex (Tableau 2.3), the median age of
the population of ordinary households in whole years (Tableau 3.4), and, in
the annex, that population by five-year age group and sex (Tableaux A.02 to
A.21). The map draws the nine regions of before 2023.

Where the regions of 2023 make an old region exactly, their figures are added:
Kayes is the regions of Kayes, Kita and Nioro; Tombouctou those of Tombouctou
and Taoudenni; Gao those of Gao and Ménaka; Kidal is Kidal. That was measured,
not assumed: OCHA's 2025 boundaries of the 2023 regions and their 160 cercles
were placed on the map's polygons point by point, and each of those regions
lies inside its old one. The others do not: the Bougouni region of 2023 took
the cercle of Ouélessébougou and part of Sélingué from Koulikoro, the Koutiala
region part of Bla from Ségou, the Ségou region (as the cercle of Nampala) part
of Ténenkou from Mopti, and the District of Bamako of 2023 is drawn about three
times the size of the district on the map, over ground the map draws in the
Kati cercle. Their figures are not put on those five polygons, which say why;
the polygons keep the figures for their own ground that other sources give.

Medians: Kidal's is the report's own; a region made of several is interpolated
within the five-year group holding the middle person, from the annex's groups
added together, after each part's interpolated median is checked against the
report's within a year.

**The cercles.** The 2022 census is published by region only. The 2009 census
(RGPH 2009) counted everyone by sex and five-year age group in each of the 50
cercles the map draws, as the US Census Bureau's subnational tables give it
(HDX); where that table carries the cercles, their median age and sex ratio
are written from it, and the people whose age was not stated are left out of
the median. Their populations are left to newer figures.

**Checks before anything is written.** Every row's men and women make its
total (the annex's counts are adjusted and may miss by a person); the regions
make the country's 22,395,489; each annex table's groups make its own total;
each 2009 cercle's groups and sexes make its total, and the cercles their
region.

Usage:
    python -m scripts.fetch_census.mali_census
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

from . import uscb
from ._shared import NOT_AVAILABLE, PROCESSED, gap, http_get, log, measure, record, write_json
from .cod_ps_age import grouped_median

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from probe_pdf import fetch_blob  # noqa: E402

URL = ("https://instat-mali.org/laravel-filemanager/files/shares/rgph/"
       "rapport-etat-structure-population-rgph5-rgph.pdf")
PAGE = ("https://www.instat-mali.org/fr/publications/"
        "recensement-general-de-la-population-et-de-lhabitat-rgph")
SOURCE = ("Institut National de la Statistique (INSTAT) du Mali, Cinquième Recensement Général "
          "de la Population et de l'Habitat (RGPH5) 2022, Rapport d'analyse, État et structure "
          "de la population (2024)")
LICENCE = "Official statistics publication of the Institut National de la Statistique du Mali"
YEAR = 2022
NATIONAL = (11_256_555, 11_138_934, 22_395_489)
DATASET = "mali-subnational-population-and-housing-data-tables-with-administrative-boundaries"
SOURCE_2009 = ("Institut National de la Statistique (INSTAT) du Mali, 4ème Recensement Général de "
               "la Population et de l'Habitat (RGPH) 2009, Résultats définitifs, Tome 1: Série "
               "démographique, population by sex and five-year age group, as the US Census "
               "Bureau tabulates it for HDX")
YEAR_2009 = 2009
OUT = "mali_census.json"
SITE = PROCESSED.parent.parent / "site" / "data"

REGIONS = ["Kayes", "Koulikoro", "Sikasso", "Ségou", "Mopti", "Tombouctou", "Gao", "Kidal",
           "Taoudenni", "Ménaka", "Nioro", "Kita", "Dioïla", "Nara", "Bougouni", "Koutiala",
           "San", "Douentza", "Bandiagara", "Bamako"]
# The map's regions (folded) made exactly of regions of 2023.
MADE_OF = {"kayes": ["Kayes", "Kita", "Nioro"], "tombouctou": ["Tombouctou", "Taoudenni"],
           "gao": ["Gao", "Ménaka"], "kidal": ["Kidal"]}
# The map's regions (folded) whose ground the regions of 2023 cross, and how.
CROSSED = {
    "koulikouro": ("the Bougouni region of 2023 took in the cercle of Ouélessébougou and part of "
                   "the cercle of Sélingué, drawn here in Koulikoro, and the District of Bamako "
                   "of 2023 takes in ground drawn here in the Kati cercle"),
    "sikasso": ("the Bougouni region of 2023 took in the cercle of Ouélessébougou and part of the "
                "cercle of Sélingué from Koulikoro, and the Koutiala region of 2023 part of the "
                "cercle of Bla from Ségou"),
    "segou": ("the Koutiala region of 2023 took in part of the cercle of Bla, drawn here in "
              "Ségou, and the Ségou region of 2023 took in, as the cercle of Nampala, part of the "
              "cercle of Ténenkou, drawn here in Mopti"),
    "mopti": ("the Ségou region of 2023 took in, as the cercle of Nampala, part of the cercle of "
              "Ténenkou, drawn here in Mopti"),
    "bamako": ("the District of Bamako of 2023 is drawn by OCHA's boundaries of the 2023 units "
               "about three times the size of the district drawn here, over ground drawn here in "
               "the Kati cercle"),
}

TRIPLE_ROW = re.compile(r"^\s*(?P<label>[^\d]+?)\s+(?P<rest>\d[\d\s,]*)$")
AGE_ROW = re.compile(r"^\s*(?P<lo>\d{1,3})\s*-\s*(?P<hi>\d{1,3})\s*ans\s+(?P<rest>.+)$")
OPEN_ROW = re.compile(r"^\s*100\s*ans\s*(?:\+|ou\s+plus)\s+(?P<rest>.+)$")
ALL_ROW = re.compile(r"^\s*Ensemble\s+(?P<rest>.+)$")
ANNEX_TITLE = re.compile(r"(?is)Tableau\s+A\s*\.\s*(\d)\s*(\d)\s*:(?:(?!Tableau).)*?"
                         r"(?:r[ée]gion\s+de|district\s+de)\s+([A-Za-zÀ-ÿ\-]+?)\s*\d*\s*"
                         r"par\s+groupes")


def fold(text: Any) -> str:
    s = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(c for c in s.lower() if c.isalpha() and not unicodedata.combining(c))


REGION_BY_FOLD = {fold(r): r for r in REGIONS}


def grouped(chunk: list[str]) -> bool:
    return (bool(chunk) and all(t.isdigit() for t in chunk) and 1 <= len(chunk[0]) <= 3
            and all(len(t) == 3 for t in chunk[1:]))


def numbers(tokens: list[str]) -> list[list[tuple[int, int]]]:
    """For each start position, the (value, end) readings of a number there:
    digits grouped in threes by spaces, or one run of digits."""
    out = []
    for i in range(len(tokens)):
        options = []
        # No number starts with a padded group ("000"): that is the middle of one.
        if tokens[i].isdigit() and not (len(tokens[i]) > 1 and tokens[i].startswith("0")):
            if len(tokens[i]) > 3:
                options.append((int(tokens[i]), i + 1))
            else:
                j = i + 1
                options.append((int(tokens[i]), j))
                while j < len(tokens) and len(tokens[j]) == 3 and tokens[j].isdigit():
                    j += 1
                    options.append((int("".join(tokens[i:j])), j))
        out.append(options)
    return out


def first_triple(text: str, slack: int = 0) -> tuple[int, int, int] | None:
    """(men, women, total): the first three numbers of a row, read off its
    digit groups, the first two making the third within ``slack``."""
    tokens = [t for t in text.replace(" ", " ").split()]
    tokens = [t for t in tokens if re.fullmatch(r"\d+", t) or re.fullmatch(r"[\d,.\-]+", t)]
    digits = []
    for t in tokens:
        if not t.isdigit():
            break
        digits.append(t)
    readings = numbers(digits)
    # An exact reading first; one within the slack only where none is exact.
    for allowed in sorted({0, slack}):
        for a, a_end in (readings[0] if readings else []):
            for b, b_end in (readings[a_end] if a_end < len(readings) else []):
                for c, c_end in (readings[b_end] if b_end < len(readings) else []):
                    if abs(a + b - c) <= allowed:
                        return a, b, c
    return None


def pages_with(text: str, pattern: str) -> list[str]:
    """The pages naming a table: its own, and the list of tables before it."""
    return [page for page in text.split("\f") if re.search(pattern, page)]


def first_reading(text: str, pattern: str, reader) -> Any:
    """The first page naming the table that reads as the table."""
    problems = []
    for page in pages_with(text, pattern):
        try:
            return reader(page)
        except SystemExit as err:
            problems.append(str(err))
    raise SystemExit(f"mali_census: no page reads as {pattern!r}: {problems}")


def parse_sexes(text: str) -> dict[str, tuple[int, int, int]]:
    """Tableau 2.3: each region of 2023 and the country, (men, women, total)."""
    return first_reading(text, r"Tableau\s*2\s*\.\s*3\s*:", sexes_on)


def sexes_on(page: str) -> dict[str, tuple[int, int, int]]:
    out: dict[str, tuple[int, int, int]] = {}
    for line in page.splitlines():
        m = TRIPLE_ROW.match(line)
        if not m:
            continue
        key = fold(m.group("label"))
        name = REGION_BY_FOLD.get(key) or ("Ensemble" if key == "ensemble" else None)
        if name is None or name in out:
            continue
        triple = first_triple(m.group("rest"))
        if triple:
            out[name] = triple
    missing = [r for r in REGIONS if r not in out]
    if missing or out.get("Ensemble") != NATIONAL:
        raise SystemExit(f"mali_census: Tableau 2.3 lacks {missing} or its total reads "
                         f"{out.get('Ensemble')}")
    # The counts are adjusted for the coverage survey and rounded one by one:
    # the regions make the country's 22,395,489 within a person or two.
    made = tuple(sum(out[r][i] for r in REGIONS) for i in range(3))
    if any(abs(made[i] - NATIONAL[i]) > 20 for i in range(3)):
        raise SystemExit(f"mali_census: the regions make {made}, not {NATIONAL}")
    return out


def parse_medians(text: str) -> dict[str, int]:
    """Tableau 3.4: each region's median age (ordinary households, whole years)."""
    return first_reading(text, r"Tableau\s*3\s*\.\s*4\s*:", medians_on)


def medians_on(page: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for line in page.splitlines():
        m = re.match(r"^\s*([^\d]+?)\s+((?:\d+,\d\s+){3}(?:\d+\s+){2}\d+)\s*$", line)
        if not m:
            continue
        name = REGION_BY_FOLD.get(fold(m.group(1)))
        if name and name not in out:
            out[name] = int(m.group(2).split()[-1])
    missing = [r for r in REGIONS if r not in out]
    if missing:
        raise SystemExit(f"mali_census: Tableau 3.4 lacks {missing}")
    return out


def parse_annex(text: str) -> dict[str, dict[str, Any]]:
    """Tableaux A.02-A.21: {region: {"groups": [(low, high or None, total)],
    "men": m, "women": w, "total": t}} for the population of ordinary households."""
    out: dict[str, dict[str, Any]] = {}
    for m in ANNEX_TITLE.finditer(text):
        number = int(m.group(1) + m.group(2))
        name = REGION_BY_FOLD.get(fold(m.group(3)))
        if not 2 <= number <= 21 or name is None or name in out:
            continue
        groups: list[tuple[int, int | None, int]] = []
        men = women = total = None
        for line in text[m.end():].splitlines():
            a, o, e = AGE_ROW.match(line), OPEN_ROW.match(line), ALL_ROW.match(line)
            if a:
                t = first_triple(a.group("rest"), slack=2)
                if t:
                    lo, hi = int(a.group("lo")), int(a.group("hi"))
                    if not groups or lo == groups[-1][1] + 1:
                        groups.append((lo, hi, t[2]))
            elif o:
                t = first_triple(o.group("rest"), slack=2)
                if t:
                    groups.append((100, None, t[2]))
            elif e and groups:
                t = first_triple(e.group("rest"), slack=2)
                if t:
                    men, women, total = t
                    break
        if total is None or not groups or groups[0][0] != 0 or groups[-1][1] is not None:
            raise SystemExit(f"mali_census: Tableau A.{number:02d} ({name}) reads "
                             f"{len(groups)} groups and no total")
        made = sum(g[2] for g in groups)
        if abs(made - total) > len(groups):
            raise SystemExit(f"mali_census: Tableau A.{number:02d} ({name}): groups make "
                             f"{made:,}, not {total:,}")
        out[name] = {"groups": groups, "men": men, "women": women, "total": total,
                     "table": f"Tableau A.{number:02d}"}
    missing = [r for r in REGIONS if r not in out]
    if missing:
        raise SystemExit(f"mali_census: the annex lacks {missing}")
    return out


def summed_groups(parts: list[str], annex: dict[str, dict[str, Any]]
                  ) -> list[tuple[int, int | None, int]]:
    shapes = {tuple((lo, hi) for lo, hi, _ in annex[p]["groups"]) for p in parts}
    if len(shapes) != 1:
        raise SystemExit(f"mali_census: {parts} have different age groups")
    first = annex[parts[0]]["groups"]
    return [(lo, hi, sum(annex[p]["groups"][i][2] for p in parts))
            for i, (lo, hi, _) in enumerate(first)]


def check_medians(annex: dict[str, dict[str, Any]], medians: dict[str, int]) -> None:
    for region in REGIONS:
        mine = grouped_median(annex[region]["groups"])
        if mine is None or abs(mine - medians[region]) > 1.0:
            raise SystemExit(f"mali_census: {region}'s groups give a median of {mine}, the "
                             f"report {medians[region]}")


def region_records(sexes: dict[str, tuple[int, int, int]], medians: dict[str, int],
                   annex: dict[str, dict[str, Any]], admin1: list[dict[str, Any]]
                   ) -> tuple[list[dict[str, Any]], list[str]]:
    records, report = [], []
    src = {"name": SOURCE, "url": URL, "page": PAGE, "license": LICENCE, "year": YEAR}
    for shape in admin1:
        key = fold(shape["name"])
        if key in MADE_OF:
            parts = MADE_OF[key]
            men, women, total = (sum(sexes[p][i] for p in parts) for i in range(3))
            if len(parts) == 1:
                median = float(medians[parts[0]])
                median_note = ("The 2022 census's median age of the region's population in "
                               "ordinary households, in whole years (Tableau 3.4).")
                pop_note = "The 2022 census's count for the region (Tableau 2.3)."
            else:
                groups = summed_groups(parts, annex)
                median = grouped_median(groups)
                listed = ", ".join(f"{p} {sexes[p][2]:,}" for p in parts[:-1])
                listed += f" and {parts[-1]} {sexes[parts[-1]][2]:,}"
                names = ", ".join(parts[:-1]) + " and " + parts[-1]
                median_note = (
                    "Interpolated within the five-year age group that holds the middle person, "
                    "from the 2022 census's count of the population of ordinary households by "
                    f"five-year age group (Tableaux A.02 to A.21), of the regions of {names} "
                    "of 2023 together.")
                pop_note = (f"The 2022 census counts the region as drawn here as the regions of "
                            f"2023 made from it: {listed} (Tableau 2.3), added here.")
            records.append(record(
                f"MLI-RGPH5-region-{key}", shape["name"], level="admin1", parent="MLI",
                country="MLI", match_by="shape_id", shape_id=shape["id"],
                population=measure(total, year=YEAR, source=SOURCE + ", Tableau 2.3"),
                population_note=pop_note,
                sex_ratio=measure(round(1000 * men / women), unit="males_per_1000_females",
                                  year=YEAR, source=SOURCE + ", Tableau 2.3"),
                median_age=measure(median, unit="years", year=YEAR, source=SOURCE),
                median_age_note=median_note,
                sources=[{**src, "field": "population/sex_ratio/median_age"}]))
            log(f"  {shape['name']}: {total:,} ({' + '.join(parts)}), "
                f"{round(1000 * men / women)} men per 1,000 women, median {median}")
        elif key in CROSSED:
            reason = (f"The 2022 census counts the regions of 2023, and their lines cross this "
                      f"region's: {CROSSED[key]}. Its sex ratio and median age cannot be put "
                      "together from the census's tables of the regions of 2023.")
            records.append(record(
                f"MLI-RGPH5-region-{key}", shape["name"], level="admin1", parent="MLI",
                country="MLI", match_by="shape_id", shape_id=shape["id"],
                median_age=gap(NOT_AVAILABLE, reason), sex_ratio=gap(NOT_AVAILABLE, reason),
                sources=[{**src, "field": "median_age/sex_ratio"}]))
            report.append(f"{shape['name']}: not the ground of any regions of 2023")
        else:
            report.append(f"region polygon {shape['name']!r}: not placed")
    return records, report


def read_2009(book) -> dict[str, Any]:
    """The 2009 census by cercle from the Bureau's Age-Sex sheet: {"cercles":
    [{name, region, median, men, women, total, stated}], "regions": {name: total},
    "blank": cercle rows without figures}."""
    rows = uscb.sheet_rows(book, "Age-Sex")
    names, _ = uscb.columns(rows)
    at = {n: i for i, n in enumerate(names) if n}
    group_cols = []
    for name, i in at.items():
        m = re.fullmatch(r"B(\d{2})(\d{2})", name)
        if m:
            group_cols.append((int(m.group(1)), int(m.group(2)), i))
        elif name == "B80PL":
            group_cols.append((80, None, i))
    group_cols.sort()
    cercles, regions, blank = [], {}, []
    for row in rows[2:]:
        level = uscb.number(row[at["ADM_LEVEL"]])
        total = uscb.number(row[at["BTOTL"]])
        if level == 1 and total:
            regions[str(row[at["ADM1_NAME"]]).strip()] = int(total)
        if level != 2:
            continue
        name = str(row[at["ADM2_NAME"]]).strip()
        region = str(row[at["ADM1_NAME"]]).strip()
        men, women = uscb.number(row[at["MTOTL"]]), uscb.number(row[at["FTOTL"]])
        groups = [(lo, hi, uscb.number(row[i])) for lo, hi, i in group_cols]
        if not total or men is None or women is None or any(g[2] is None for g in groups):
            blank.append(f"{region}/{name}")
            continue
        unstated = uscb.number(row[at["B_NS"]]) if "B_NS" in at else 0.0
        stated = sum(g[2] for g in groups)
        if abs(stated + (unstated or 0) - total) > 1 or abs(men + women - total) > 1:
            raise SystemExit(f"mali_census: 2009 {region}/{name}: groups {stated:,.0f} + "
                             f"{unstated or 0:,.0f} unstated, sexes {men + women:,.0f}, total "
                             f"{total:,.0f}")
        cercles.append({"name": name, "region": region, "median": grouped_median(groups),
                        "men": int(men), "women": int(women), "total": int(total),
                        "unstated": int(unstated or 0)})
    for region, total in regions.items():
        made = sum(c["total"] for c in cercles if c["region"] == region)
        if cercles and made and made != total:
            raise SystemExit(f"mali_census: 2009 {region}'s cercles make {made:,}, not {total:,}")
    return {"cercles": cercles, "regions": regions, "blank": blank}


def cercle_records(data: dict[str, Any], admin1: list[dict[str, Any]],
                   admin2: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    parents = {s["id"]: fold(s["name"]).replace("koulikouro", "koulikoro") for s in admin1}
    by_key = {(fold(c["region"]), fold(c["name"])): c for c in data["cercles"]}
    records, report, used = [], [], set()
    src = {"name": SOURCE_2009, "url": uscb.dataset_url(DATASET), "year": YEAR_2009,
           "license": "CC BY-IGO, published via HDX"}
    for shape in admin2:
        key = (parents.get(shape["parent"], ""), fold(shape["name"]))
        c = by_key.get(key)
        if c is None:
            report.append(f"cercle polygon {shape['name']!r}: no 2009 row")
            continue
        used.add(key)
        share = 100 * c["unstated"] / c["total"]
        records.append(record(
            f"MLI-RGPH2009-{key[0]}-{key[1]}", shape["name"], level="admin2", parent="MLI",
            country="MLI", match_by="shape_id", shape_id=shape["id"],
            median_age=measure(c["median"], unit="years", year=YEAR_2009, source=SOURCE_2009),
            median_age_note=(
                "Interpolated within the five-year age group that holds the middle person, from "
                "the 2009 census's count of the cercle by five-year age group; the "
                f"{share:.1f}% whose age was not stated are left out. The 2022 census is "
                "published by region only."),
            sex_ratio=measure(round(1000 * c["men"] / c["women"]), unit="males_per_1000_females",
                              year=YEAR_2009, source=SOURCE_2009),
            sex_ratio_note="The 2009 census's count; the 2022 census is published by region only.",
            sources=[{**src, "field": "median_age/sex_ratio"}]))
    left = sorted(f"{c['region']}/{c['name']}" for k, c in by_key.items() if k not in used)
    if left:
        report.append(f"2009 cercles not placed: {left}")
    return records, report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", default="", help="a label that tells one dispatch from another")
    ap.parse_args()
    from pypdf import PdfReader
    import openpyxl

    blob = fetch_blob(URL)
    if not blob.startswith(b"%PDF"):
        raise SystemExit(f"mali_census: {URL} is not a PDF: {blob[:60]!r}")
    log(f"  read {URL}: {len(blob):,} bytes, sha256 {hashlib.sha256(blob).hexdigest()}")
    text = "\f".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(blob)).pages)
    sexes = parse_sexes(text)
    medians = parse_medians(text)
    annex = parse_annex(text)
    check_medians(annex, medians)
    for region in REGIONS:
        log(f"  {region}: {sexes[region][2]:,} ({sexes[region][0]:,} men), median "
            f"{medians[region]}, annex {annex[region]['total']:,} in ordinary households, "
            f"interpolated {grouped_median(annex[region]['groups'])}")
    admin1 = json.loads((SITE / "admin1" / "MLI.units.json").read_text())
    admin2 = json.loads((SITE / "admin2" / "MLI.units.json").read_text())
    records, report = region_records(sexes, medians, annex, admin1)

    url = uscb.workbook_url(DATASET)
    book = openpyxl.load_workbook(io.BytesIO(http_get(url, binary=True, cache=False)),
                                  read_only=True, data_only=True)
    data = read_2009(book)
    log(f"  2009: {len(data['cercles'])} cercles with figures, {len(data['blank'])} blank, "
        f"{len(data['regions'])} regions")
    if data["cercles"]:
        more, why = cercle_records(data, admin1, admin2)
        records += more
        report += why
    for line in report:
        log("  " + line)
    log(f"  {sum(1 for r in records if r['level'] == 'admin1')} regions and "
        f"{sum(1 for r in records if r['level'] == 'admin2')} cercles written")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
