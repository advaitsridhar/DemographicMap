#!/usr/bin/env python3
"""Luxembourg: population, median age and sex ratio by commune and canton, RP 2021.

STATEC publishes the 2021 census (Recensement de la population, 8 November
2021) on LUSTAT, its .Stat Suite, and one dataflow carries age and sex by
commune: DSD_CENSUS_GROUP1_3@DF_B1607, "Population by canton and
municipality, sex and age", in five-year groups (0-4 ... 95-99, then 100 and
over) for the 102 communes of 2021 and the 12 cantons. It is the finest
geography at which STATEC publishes age -- its annual population table by
commune carries no age -- so the median is interpolated within the
five-year group that holds the middle person, and each note says so.

**Vintage.** The map draws Luxembourg's 105 communes of 2015-2017. Three
mergers since then fall inside the map: Habscht (Hobscheid and Septfontaines,
2018), Helperknapp (Boevange-sur-Attert and Tuntange, 2018) and
Rosport-Mompach (2018), so the census counts those three merged communes and
not their six drawn parts, whose polygons are left out rather than given a
merged commune's figure. Groussbus-Wal (Grosbous and Wahl) and
Bous-Waldbredimus merged in 2023, after the census, which still counts their
four parts separately; they fit the map. The cantons have not changed.

Usage:
    python -m scripts.fetch_census.luxembourg
"""

from __future__ import annotations

import argparse
import csv
import io
import re
from collections import Counter
from typing import Any

from ._shared import PROCESSED, http_get, log, record, write_json
from .central_ages import age_sex_fields, check_national_median, check_sum, fold, report_unbound, units

DATA = ("https://lustat.statec.lu/rest/data/LU1,DSD_CENSUS_GROUP1_3@DF_B1607,1.0/all"
        "?dimensionAtObservation=AllDimensions")
PORTAL = "https://lustat.statec.lu/"
SOURCE = "STATEC, Recensement de la population 2021, LUSTAT DF_B1607"
LICENCE = "CC BY 4.0 (STATEC)"
OUT = PROCESSED / "luxembourg_commune.json"
YEAR = 2021
# The census's communes that merged drawn ones, which the map does not draw.
MERGED_SINCE_MAP = {"Habscht": ("Hobscheid", "Septfontaines"),
                    "Helperknapp": ("Boevange-sur-Attert", "Tuntange"),
                    "Rosport-Mompach": ("Rosport", "Mompach")}
# The boundary file's spellings where they differ from STATEC's.
MAP_NAMES = {"Vallée de l'Ernz": "Vallbe de l'Ernz", "Redange": "Redange/Attert",
             "Redange-sur-Attert": "Redange/Attert"}


def read() -> tuple[dict[str, str], dict[str, dict[str, Counter]], dict[str, float]]:
    """GEO labels, {geo: {"M"/"F": Counter{(first, last): n}}}, and {geo: total}."""
    blob = http_get(DATA, headers={"Accept": "application/vnd.sdmx.data+csv;version=1.0.0;labels=both"},
                    timeout=300)
    rows = list(csv.DictReader(io.StringIO(blob)))
    if not rows:
        raise SystemExit("luxembourg: DF_B1607 came back empty")
    col = {k.split(":")[0]: k for k in rows[0]}
    labels: dict[str, str] = {}
    counts: dict[str, dict[str, Counter]] = {}
    totals: dict[str, float] = {}
    for row in rows:
        geo_code, _, geo_label = row[col["GEO"]].partition(": ")
        labels[geo_code] = geo_label.strip() or geo_code
        sex = row[col["SEX"]].split(":")[0]
        age = row[col["AGE"]].split(":")[0]
        value = float(row[col["OBS_VALUE"]] or 0)
        if age == "_T" and sex == "_T":
            totals[geo_code] = value
            continue
        if sex not in ("M", "F"):
            continue
        m = re.fullmatch(r"Y(\d+)T(\d+)", age)
        if m and int(m.group(2)) - int(m.group(1)) == 4:
            key = (int(m.group(1)), int(m.group(2)))
        elif age == "Y_LT5":
            key = (0, 4)
        elif age == "Y_GE100":
            key = (100, None)
        else:
            continue                  # an aggregate over the five-year groups
        counts.setdefault(geo_code, {"M": Counter(), "F": Counter()})[sex][key] += value
    for geo, by_sex in counts.items():
        starts = sorted(a for a, _ in by_sex["M"] | by_sex["F"])
        if starts != list(range(0, 101, 5)):
            raise SystemExit(f"luxembourg: {labels.get(geo, geo)} has age groups {starts}")
    return labels, counts, totals


def build() -> list[dict[str, Any]]:
    log("luxembourg: RP 2021 by commune, sex and five-year age group (LUSTAT DF_B1607)")
    labels, counts, totals = read()
    national = totals.get("_T")
    # A commune's code is its LAU code, LU0000 and three digits; the cantons
    # share several communes' names (Luxembourg, Wiltz, Mersch) and are told
    # apart by code, never by label.
    communes = sorted(g for g in counts if re.fullmatch(r"LU0000\d{3}", g))
    cantons = sorted(g for g in counts if g != "_T" and g not in communes)
    log(f"  {len(communes)} communes, {len(cantons)} cantons, Luxembourg {national:,.0f}")
    if len(communes) != 102 or len(cantons) != 12:
        raise SystemExit(f"luxembourg: expected 102 communes and 12 cantons; the labels are "
                         f"{sorted(labels.values())}")
    for geo in [*communes, *cantons]:
        made = sum(counts[geo]["M"].values()) + sum(counts[geo]["F"].values())
        if abs(made - totals[geo]) > 0.5:
            raise SystemExit(f"luxembourg: {labels[geo]}: the groups make {made:,.0f}, "
                             f"the total is {totals[geo]:,.0f}")
    check_sum((totals[g] for g in communes), national, "communes against Luxembourg")
    check_sum((totals[g] for g in cantons), national, "cantons against Luxembourg")
    both = Counter()
    for geo in communes:
        both.update(counts[geo]["M"])
        both.update(counts[geo]["F"])
    check_national_median(both, "LU", YEAR + 1, groups=True, tolerance=0.6)

    records = []
    note = ("Interpolated within the five-year age group that holds the middle person, from "
            "STATEC's census count of the {what} on 8 November 2021 by sex and five-year age "
            "group; STATEC publishes age by commune in five-year groups only.")
    for level, geos, what in (("admin2", communes, "commune"), ("admin1", cantons, "canton")):
        shapes = units("LUX", level)
        by_key: dict[str, list[dict[str, Any]]] = {}
        for shape in shapes:
            by_key.setdefault(fold(shape["name"]), []).append(shape)
        unbound, used = [], set()
        for geo in geos:
            name = labels[geo]
            if name in MERGED_SINCE_MAP:
                log(f"  {name}: merged in 2018 from {' and '.join(MERGED_SINCE_MAP[name])}, "
                    f"which the map draws apart; not written")
                continue
            drawn = MAP_NAMES.get(name, name)
            keys = [fold(drawn)] if level == "admin2" else [fold("Canton " + drawn.replace("Canton ", "")),
                                                              fold(drawn)]
            hits = next((by_key[k] for k in keys if by_key.get(k)), [])
            if len(hits) != 1 or hits[0]["id"] in used:
                unbound.append(f"{name} ({geo})")
                continue
            shape = hits[0]
            used.add(shape["id"])
            fields = age_sex_fields(
                counts[geo]["M"], counts[geo]["F"], year=YEAR, source=SOURCE, total=totals[geo],
                groups=True, median_note=note.format(what=what),
                ratio_note=f"Males per 100 females counted in the {what} by the 2021 census.")
            records.append(record(
                f"LUX-RP2021-{geo}", name, level=level,
                parent="LUX" if level == "admin1" else shape["parent"], country="LUX",
                codes={"statec_geo": geo}, aliases=[shape["name"]] if shape["name"] != name else [],
                match_by="shape_id", shape_id=shape["id"],
                sources=[{"field": "population/median_age/sex_ratio", "name": SOURCE,
                          "url": PORTAL, "license": LICENCE, "year": YEAR}],
                **fields))
        left = [s["name"] for s in shapes if s["id"] not in used]
        report_unbound(f"luxembourg {level}", unbound, left)
        expected_left = {n for parts in MERGED_SINCE_MAP.values() for n in parts} if level == "admin2" else set()
        if unbound or set(left) != expected_left:
            raise SystemExit(f"luxembourg: {level} does not pair up: {unbound} / {left}")
    return records


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.parse_args()
    records = build()
    write_json(OUT, records)
    log(f"  wrote {OUT.name}: {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
