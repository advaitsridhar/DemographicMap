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
not their six drawn parts, which are never given a merged commune's figure.
Groussbus-Wal (Grosbous and Wahl) and Bous-Waldbredimus merged in 2023, after
the census, which still counts their four parts separately; they fit the map.
The cantons have not changed.

**The six drawn parts** take STATEC's last figures for exactly those communes,
from its files on data.public.lu: the population on 1 January 2017
(``popcom2000-2017_LAU2.xlsx``, the year before the merger), and median age
and sex ratio from the 2011 census (population of usual residence on 1
February 2011, by commune and five-year age group, and by commune and sex).
Each file is checked against its own national total, and each field says its
year.

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

from ._shared import PROCESSED, http_get, log, measure, record, write_json
from .central_ages import (SEX_RATIO_UNIT, age_sex_fields, check_national_median, check_sum, fold,
                           median_of_groups, report_unbound, sex_ratio, units)

DATA = ("https://lustat.statec.lu/rest/data/LU1,DSD_CENSUS_GROUP1_3@DF_B1607,1.0/all"
        "?dimensionAtObservation=AllDimensions")
PORTAL = "https://lustat.statec.lu/"
SOURCE = "STATEC, Recensement de la population 2021, LUSTAT DF_B1607"
LICENCE = "CC BY 4.0 (STATEC)"
OUT = PROCESSED / "luxembourg_commune.json"
YEAR = 2021
LUXDATA = "https://download.data.public.lu/resources/"
POPCOM = (LUXDATA + "population-par-commune-et-code-lau2-depuis-2000/20170511-141118/"
          "popcom2000-2017_LAU2.xlsx")
RP2011_AGE = (LUXDATA + "population-de-residence-habituelle-par-commune-et-age-au-1er-fevrier-2011/"
              "20160711-131312/Population_par_commune_et_age_au_1er_fevrier_2011.xlsx")
RP2011_SEX = (LUXDATA + "population-de-residence-habituelle-par-commune-et-sexe-au-1er-fevrier-2011/"
              "20160711-131552/Population_par_commune_et_sexe_au_1er_fevrier_2011.xlsx")
POPCOM_SOURCE = "STATEC, Population par commune et code LAU2 depuis 2000 (1 January 2017)"
RP2011_SOURCE = "STATEC, Recensement de la population 2011 (1 February 2011), population by commune"
POPCOM_COLUMN = "1-1-2017"
# STATEC's older files write one of the six differently from the map.
OLD_NAMES = {"Boevange-sur-Attert": "Boevange-Attert"}
# The census's communes that merged drawn ones, which the map does not draw.
MERGED_SINCE_MAP = {"Habscht": ("Hobscheid", "Septfontaines"),
                    "Helperknapp": ("Boevange-sur-Attert", "Tuntange"),
                    "Rosport-Mompach": ("Rosport", "Mompach")}
# The boundary file's spellings where they differ from STATEC's.
MAP_NAMES = {"Vallée de l'Ernz": "Vallbe de l'Ernz", "Redange": "Redange/Attert",
             "Redange-sur-Attert": "Redange/Attert", "Canton Esch": "Canton Esch-sur-Alzette"}


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
    # SDMX leaves out a cell that is zero, so a small commune with nobody
    # over 90 simply has no older groups; what is present must be the grid.
    grid = set(range(0, 101, 5))
    for geo, by_sex in counts.items():
        starts = {a for a, _ in by_sex["M"] | by_sex["F"]}
        if not starts <= grid or not {0, 5, 10} <= starts:
            raise SystemExit(f"luxembourg: {labels.get(geo, geo)} has age groups {sorted(starts)}")
    return labels, counts, totals


def build() -> list[dict[str, Any]]:
    log("luxembourg: RP 2021 by commune, sex and five-year age group (LUSTAT DF_B1607)")
    labels, counts, totals = read()
    national = totals.get("_T")
    # The codes do not follow one pattern (the communes' LAU codes vary in
    # length), but every canton's label reads "Canton X", which is also how
    # the cantons that share a commune's name (Luxembourg, Wiltz, Mersch) are
    # told apart from it.
    cantons = sorted(g for g in counts if g != "_T" and labels.get(g, "").startswith("Canton "))
    communes = sorted(g for g in counts if g != "_T" and g not in cantons)
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
    check_national_median(both, "LU", YEAR + 1, groups=True)

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
            name = labels[geo].replace(" - ", "-")      # STATEC writes "Rosport - Mompach"
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
        if level == "admin2":
            records += premerger_records([s for s in shapes if s["id"] not in used])
        expected_left = {n for parts in MERGED_SINCE_MAP.values() for n in parts} if level == "admin2" else set()
        if unbound or set(left) != expected_left:
            raise SystemExit(f"luxembourg: {level} does not pair up: {unbound} / {left}")
    return records


def book_rows(url: str) -> list[list[Any]]:
    """The first sheet of one of STATEC's .xlsx files, as rows of cells."""
    import openpyxl
    book = openpyxl.load_workbook(io.BytesIO(http_get(url, binary=True, timeout=120)),
                                  read_only=True, data_only=True)
    return [list(r) for r in book.worksheets[0].iter_rows(values_only=True)]


def text_of(cell: Any) -> str:
    return " ".join(str(cell if cell is not None else "").split())


def read_popcom(rows: list[list[Any]]) -> tuple[dict[str, float], float]:
    """{commune: population on 1 January 2017} and the file's own total."""
    head = next(i for i, r in enumerate(rows) if POPCOM_COLUMN in [text_of(c) for c in r])
    col = [text_of(c) for c in rows[head]].index(POPCOM_COLUMN)
    out, total = {}, None
    for r in rows[head + 1:]:
        first = text_of(r[0])
        if "Total" in (first, text_of(r[1] if len(r) > 1 else "")):
            total = float(r[col])
        elif re.fullmatch(r"\d{1,4}", first) and isinstance(r[col], (int, float)):
            out[text_of(r[1])] = float(r[col])
    if total is None:
        raise SystemExit("luxembourg: the 2000-2017 file has no Total row")
    check_sum(out.values(), total, f"communes on {POPCOM_COLUMN} against Luxembourg")
    return out, total


def read_rp2011_ages(rows: list[list[Any]]) -> dict[str, Counter]:
    """{commune: Counter{(first, last or None): n}} from the 2011 census's five-year groups."""
    head = next(i for i, r in enumerate(rows) if any(text_of(c) == "0 à 4 ans" for c in r))
    labels = [text_of(c) for c in rows[head]]
    groups: dict[int, tuple[int, int | None]] = {}
    for j, label in enumerate(labels):
        m = re.fullmatch(r"(\d+) à (\d+) ans", label)
        if m:
            groups[j] = (int(m.group(1)), int(m.group(2)))
        elif re.fullmatch(r"(\d+) et plus", label):
            groups[j] = (int(label.split()[0]), None)
    total_col = labels.index("Total")
    if sorted(a for a, _ in groups.values()) != list(range(0, 101, 5)):
        raise SystemExit(f"luxembourg: the 2011 age groups are {labels}")
    out: dict[str, Counter] = {}
    for r in rows[head + 1:]:
        name = text_of(r[0])
        if not name or not isinstance(r[total_col], (int, float)):
            continue
        counts = Counter({g: float(r[j] or 0) for j, g in groups.items()})
        if abs(sum(counts.values()) - float(r[total_col])) > 0.5:
            raise SystemExit(f"luxembourg: 2011 {name}: the age groups make {sum(counts.values()):,.0f}, "
                             f"the total is {r[total_col]:,.0f}")
        out[name] = counts
    return out


def read_rp2011_sexes(rows: list[list[Any]]) -> dict[str, tuple[float, float]]:
    """{commune: (men, women)} from the 2011 census, each checked against its total."""
    head = next(i for i, r in enumerate(rows) if "Masculin" in [text_of(c) for c in r])
    labels = [text_of(c) for c in rows[head]]
    m_col, f_col, t_col = labels.index("Masculin"), labels.index("Féminin"), labels.index("Total")
    out: dict[str, tuple[float, float]] = {}
    for r in rows[head + 1:]:
        name = text_of(r[0])
        if not name or not isinstance(r[t_col], (int, float)):
            continue
        if abs(float(r[m_col]) + float(r[f_col]) - float(r[t_col])) > 0.5:
            raise SystemExit(f"luxembourg: 2011 {name}: men and women do not make its total")
        out[name] = (float(r[m_col]), float(r[f_col]))
    return out


def premerger_records(shapes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The six communes merged in 2018, from STATEC's last figures for each."""
    pop2017, _ = read_popcom(book_rows(POPCOM))
    ages = read_rp2011_ages(book_rows(RP2011_AGE))
    sexes = read_rp2011_sexes(book_rows(RP2011_SEX))
    national = ages.pop("Total", None)
    if national is None or abs(sum(sum(c.values()) for c in ages.values()) - sum(national.values())) > 0.5:
        raise SystemExit("luxembourg: the 2011 communes' age groups do not make the country's")
    men, women = sexes.pop("Total", (None, None))
    if men is None or abs(sum(m + f for m, f in sexes.values()) - (men + women)) > 0.5:
        raise SystemExit("luxembourg: the 2011 communes' sexes do not make the country's")
    check_national_median(national, "LU", 2011, groups=True)
    out = []
    for shape in shapes:
        merged = next((m for m, parts in MERGED_SINCE_MAP.items() if shape["name"] in parts), None)
        if merged is None:
            raise SystemExit(f"luxembourg: polygon {shape['name']} is not one of the six merged in 2018")
        name = OLD_NAMES.get(shape["name"], shape["name"])
        if name not in pop2017 or name not in ages or name not in sexes:
            raise SystemExit(f"luxembourg: STATEC's older files do not all name {name}")
        m, f = sexes[name]
        if abs(sum(ages[name].values()) - (m + f)) > 0.5:
            raise SystemExit(f"luxembourg: {name}: the 2011 age and sex tables disagree")
        why = (f"{shape['name']} merged into {merged} in 2018, and the 2021 census counts {merged} as "
               f"one commune; the map draws the communes of 2015-2017, so this polygon takes STATEC's "
               f"last figures for the commune itself.")
        out.append(record(
            f"LUX-2017-{fold(shape['name'])}", shape["name"], level="admin2", parent=shape["parent"],
            country="LUX", codes={"statec_name": name}, match_by="shape_id", shape_id=shape["id"],
            aliases=[name] if name != shape["name"] else [],
            population=measure(int(pop2017[name]), year=2017, source=POPCOM_SOURCE),
            population_note=f"STATEC's population of the commune on 1 January 2017. {why}",
            median_age=measure(median_of_groups([(a, b, n) for (a, b), n in ages[name].items()]),
                               unit="years", year=2011, source=RP2011_SOURCE),
            median_age_note=(f"Interpolated within the five-year age group that holds the middle "
                             f"person, from the 2011 census's population of usual residence by "
                             f"commune and five-year age group (1 February 2011). {why}"),
            sex_ratio=measure(sex_ratio(m, f), unit=SEX_RATIO_UNIT, year=2011, source=RP2011_SOURCE),
            sex_ratio_note=f"Males per 100 females counted by the 2011 census. {why}",
            sources=[{"field": "population", "name": POPCOM_SOURCE, "url": POPCOM,
                      "license": LICENCE, "year": 2017},
                     {"field": "median_age/sex_ratio", "name": RP2011_SOURCE, "url": RP2011_AGE,
                      "license": LICENCE, "year": 2011}]))
        log(f"  {shape['name']}: {int(pop2017[name]):,} (2017); 2011 census {m + f:,.0f}")
    return out


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
