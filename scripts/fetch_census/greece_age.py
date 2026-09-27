#!/usr/bin/env python3
"""Greece: median age and sex ratio for the decentralized administrations, and
why Mount Athos has neither.

The map draws Greece's first level as its seven decentralized administrations
(and Mount Athos), each a group of whole regions -- the NUTS 2 regions for
which Eurostat publishes ELSTAT's population on 1 January by single year of
age and sex (``demo_r_d2jan``). Eurostat's own median age is by NUTS 2 and
NUTS 3, never by these groupings, so five of the seven had none; Attica and
Crete are one region each and already carry Eurostat's figure. This sums
the regions' single years for each administration and interpolates the median
within the single year that holds the middle person; sex ratio is males per
100 females. The year is Eurostat's latest, the same as the regions' own
figures beside these.

Mount Athos is a self-governed monastic community inside the Central
Macedonia region for statistics: no Eurostat region is it alone, and ELSTAT's
2021 census tables by region and age do not separate it. Women may not enter
it, so a ratio of men to women is not defined there.

Usage:
    python -m scripts.fetch_census.greece_age
"""

from __future__ import annotations

import argparse
from collections import Counter
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, gap, http_get, http_json, log, measure, record, write_json
from common import NOT_APPLICABLE  # noqa: E402
from .balkans_common import check_sum, median_age, shapes
from .eurostat import API, unpack

OUT = "greece_age.json"
DATASET = "demo_r_d2jan"
SOURCE = ("Eurostat, population on 1 January by age, sex and NUTS 2 region (demo_r_d2jan), "
          "from ELSTAT; summed over the administration's regions")
# The map's first-level units -> the NUTS 2 regions each is made of.
ADMINISTRATIONS = {
    "Macedonia-Thrace": ("EL51", "EL52"),
    "Epirus-Western Macedonia": ("EL53", "EL54"),
    "Thessalia-Central Greece": ("EL61", "EL64"),
    "Peloponisos-W. Greece & Ionian": ("EL62", "EL63", "EL65"),
    "Egean": ("EL41", "EL42"),
}
ATHOS = "Agion Oros"
RESIDENT = ("https://www.statistics.gr/documents/20181/17286366/mon_plith_2021.xlsx/"
            "7adf2ca4-0baf-7b19-2860-1e7caea81e7f")
RESIDENT_PAGE = "https://www.statistics.gr/el/2021-census-res-pop-results"
ATHOS_SOURCE = ("ELSTAT, 2021 Population-Housing Census, resident population by region, "
                "regional unit and municipality (mon_plith_2021.xlsx)")


def ages(geos: list[str]) -> tuple[int, dict[str, dict[str, Counter]], dict[str, dict[str, float]]]:
    """(year, {geo: {sex: Counter(age: n)}}, {geo: {sex: total}}) for the latest year."""
    url = API.format(dataset=DATASET) + "&unit=NR&lastTimePeriod=1" + "".join(
        f"&geo={g}" for g in geos) + "&sex=M&sex=F"
    payload = http_json(url, timeout=300)
    dims = payload["id"]
    year = int(next(iter(payload["dimension"]["time"]["category"]["index"])))
    out: dict[str, dict[str, Counter]] = {g: {"M": Counter(), "F": Counter()} for g in geos}
    totals: dict[str, dict[str, float]] = {g: {"M": 0.0, "F": 0.0} for g in geos}
    unknown = 0.0
    for key, value in unpack(payload).items():
        k = dict(zip(dims, key))
        age, geo, sex = k["age"], k["geo"], k["sex"]
        if age == "TOTAL":
            totals[geo][sex] = value
        elif age == "UNK":
            unknown += value
        elif age == "Y_LT1":
            out[geo][sex][0] += value
        elif age == "Y_OPEN":
            out[geo][sex][100] += value
        elif age.startswith("Y") and age[1:].isdigit():
            out[geo][sex][int(age[1:])] += value
    for g in geos:
        for sex in ("M", "F"):
            check_sum(sum(out[g][sex].values()), totals[g][sex], f"greece_age: ages of {g} {sex}")
    if unknown:
        log(f"  {unknown:,.0f} people of unknown age, left out")
    return year, out, totals


def build() -> list[dict[str, Any]]:
    geos = sorted({g for regions in ADMINISTRATIONS.values() for g in regions})
    year, by_geo, totals = ages(geos)
    log(f"  {DATASET}, {year}: {len(geos)} regions")
    admin1 = {s["name"]: s for s in shapes("GRC", "admin1")}
    admin2 = {s["name"]: s for s in shapes("GRC", "admin2")}
    missing = [n for n in list(ADMINISTRATIONS) + [ATHOS] if n not in admin1]
    if missing:
        raise SystemExit(f"greece_age: no first-level polygon for {missing}")
    records = []
    for name, regions in ADMINISTRATIONS.items():
        pooled: Counter = Counter()
        men = women = 0.0
        for g in regions:
            pooled.update(by_geo[g]["M"])
            pooled.update(by_geo[g]["F"])
            men += totals[g]["M"]
            women += totals[g]["F"]
        median = median_age(pooled)
        shape = admin1[name]
        records.append(record(
            f"GRC-{DATASET}-{shape['id']}", name, level="admin1", parent="GRC", country="GRC",
            match_by="shape_id", shape_id=shape["id"],
            median_age=measure(median, unit="years", year=year, source=SOURCE),
            median_age_note=("Interpolated within the single year of age that holds the middle "
                             f"person, from Eurostat's population by single year of age of the "
                             f"regions {', '.join(regions)}, summed."),
            sex_ratio=measure(round(100 * men / women, 1), unit="males_per_100_females",
                              year=year, source=SOURCE),
            sources=[{"field": "median_age/sex_ratio", "name": SOURCE,
                      "url": API.format(dataset=DATASET), "year": year}]))
        log(f"  {name} ({'+'.join(regions)}): {men + women:,.0f}, median {median}, "
            f"{round(100 * men / women, 1)} men per 100 women")
    total, men, women = athos()
    why_age = ("Mount Athos is counted inside the Central Macedonia region by Eurostat, and "
               "ELSTAT's 2021 census tables by age stop at the region, so no age structure is "
               "published for it alone.")
    why_sex = (f"ELSTAT's 2021 census counts {total:,} residents on Mount Athos, {men:,} men and "
               f"{women:,} women -- women may not enter it -- so a ratio of men to women is not "
               "defined.")
    if women:
        raise SystemExit(f"greece_age: ELSTAT counts {women} women on Mount Athos; the stated "
                         "reason for its sex ratio no longer holds")
    for level, table in (("admin1", admin1), ("admin2", admin2)):
        if ATHOS in table:
            records.append(record(
                f"GRC-athos-{level}", ATHOS, level=level, parent="GRC", country="GRC",
                match_by="shape_id", shape_id=table[ATHOS]["id"],
                population=measure(total, year=2021, source=ATHOS_SOURCE),
                median_age=gap(NOT_AVAILABLE, why_age), sex_ratio=gap(NOT_APPLICABLE, why_sex),
                sources=[{"field": "population", "name": ATHOS_SOURCE, "url": RESIDENT,
                          "page": RESIDENT_PAGE, "year": 2021}]))
    return records


def athos() -> tuple[int, int, int]:
    """Mount Athos's 2021 resident population, men and women, from ELSTAT's table
    of the resident population by region, regional unit and municipality."""
    import io
    import openpyxl
    blob = http_get(RESIDENT, binary=True, timeout=300)
    rows = [tuple(r) for r in openpyxl.load_workbook(io.BytesIO(blob), read_only=True,
                                                     data_only=True).worksheets[0].iter_rows(values_only=True)]
    import unicodedata

    def plain(cell: object) -> str:
        text = unicodedata.normalize("NFKD", " ".join(str(cell or "").split()).lower())
        return "".join(c for c in text if not unicodedata.combining(c))
    header = [plain(c) for c in rows[0]]

    def column(*words: str) -> int:
        hits = [j for j, h in enumerate(header) if all(w in h for w in words)]
        if len(hits) != 1:
            raise SystemExit(f"greece_age: no single column with {words} in {header}")
        return hits[0]
    col = {"total": column("μονιμος", "2021"), "men": column("αρρεν", "2021"),
           "women": column("θηλ", "2021")}
    hit = [r for r in rows[1:] if str(r[2] or "").startswith("ΑΓΙΟ ΟΡΟΣ") and str(r[0]) == "4"]
    if len(hit) != 1:
        raise SystemExit(f"greece_age: {len(hit)} rows for Mount Athos in ELSTAT's table")
    r = hit[0]
    total, men, women = (int(r[col[k]] or 0) for k in ("total", "men", "women"))
    if men + women != total:
        raise SystemExit(f"greece_age: Mount Athos's sexes {men} + {women} against {total}")
    log(f"  Mount Athos: {total:,} residents in 2021, {men:,} men, {women:,} women")
    return total, men, women


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.parse_args()
    log("greece_age: Eurostat single years of age for Greece's decentralized administrations")
    records = build()
    write_json(PROCESSED / OUT, records)
    log(f"  wrote {OUT}: {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
