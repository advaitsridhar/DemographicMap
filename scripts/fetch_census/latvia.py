#!/usr/bin/env python3
"""Latvia: the 43 municipalities and 589 parishes and towns the map draws, from CSB.

**What the map draws.** The admin1 layer is the municipalities of the 2021
reform -- 36 novadi and the 7 state cities that stand outside them -- with
Madona and Varakļāni still apart (they merged on 1 July 2025). The admin2
layer is the territorial units inside them: 511 parishes (pagasti) and 78
towns and state cities.

**admin1** -- table IRD041 (population by municipality, single year of age and
sex, beginning of year) for population and sex ratio, and IRD031 for the
median age, which CSB computes and publishes for exactly these units; IRE031
(population by ethnicity) for the ethnicity. All at the beginning of the
latest year, except Madona and Varakļāni, which CSB lists apart only until
2025: those two are read at the beginning of 2025. Jēkabpils, Ogre and
Valmiera are state cities inside their novadi and are not added to them a
second time.

**admin2** -- table IRD081 (population by sex and five-year age group by
territorial unit, beginning of year), the finest age CSB publishes below the
municipality; the median is interpolated within the five-year group that holds
the middle person, and the note says so. RIG040 (population by ethnicity by
territorial unit, CSB's experimental statistics on the boundaries of the
latest year) for the ethnicity. Three parishes lost their centre to a new town
after the map's boundaries were drawn -- CSB gave each a new code when it did
(Ādažu 401, Ķekavas 421, Mārupes 411) -- and the map draws the parish whole,
without the town: the town and the parish are added together for it, and only
while the town has no polygon of its own.

Religion is not asked by Latvia's census (existing policy). Language was last
asked in the 2011 census, which CSB tabulates by the municipalities of 2009-
2021, not by the units drawn here; see the report.

Checks: single years and age groups make each unit's total, males and
females make it, the municipalities make the country, and each municipality's
parishes and towns make it.

Usage:
    python -m scripts.fetch_census.latvia
"""

from __future__ import annotations

import argparse
import re
from collections import defaultdict
from typing import Any

from ._shared import PROCESSED, log, measure, record, shares, write_json
from .binding import fold
from .cod_ps_age import grouped_median
from .nordic_common import (SEX_RATIO_UNIT, AgeSex, bind_rows, check_parts, load_units,
                            parent_names, request_json, sex_ratio, unplaced)
from .pxweb import unstack

EN = "https://data.stat.gov.lv/api/v1/en/OSP_PUB/POP/IR"
LV = "https://data.stat.gov.lv/api/v1/lv/OSP_PUB/POP/IR"
TABLES = {"IRD041": "IRD/IRD041", "IRD031": "IRD/IRD031", "IRE031": "IRE/IRE031",
          "IRD081": "IRD/IRD081", "RIG040": "IRE/RIG040"}
PAGE = "https://data.stat.gov.lv/pxweb/en/OSP_PUB/START__POP__IR__{folder}/{table}/"
SOURCE = "Central Statistical Bureau of Latvia"
OUT = PROCESSED / "latvia_territorial.json"

STATE_CITIES = ("LV0001000", "LV0002000", "LV0003000", "LV0004000", "LV0005000",
                "LV0006000", "LV0007000")
# Madona before its merger with Varakļāni, and Varakļāni: CSB's own codes for
# the two municipalities the map draws, which it lists until 2025.
PRE_MERGER = ("LV0038000", "LV0055000")
# The parishes whose centre became a town after the map's boundaries: the town
# (not drawn) and the parish (recoded) make the drawn parish.
REJOINED = {"LV0023401": "LV0023200", "LV0034421": "LV0034200", "LV0039411": "LV0039200"}

ETHNICITY = {"Latvians": "Latvian", "Russians": "Russian", "Belarusians": "Belarusian",
             "Ukrainians": "Ukrainian", "Poles": "Polish", "Lithuanians": "Lithuanian",
             "Jews": "Jewish", "Roma": "Roma", "Germans": "German", "Estonians": "Estonian",
             "Tatars": "Tatar", "Armenians": "Armenian", "Azerbaijanis": "Azerbaijani",
             "Moldavians": "Moldovan", "Indians": "Indian", "Georgians": "Georgian",
             "Uzbeks": "Uzbek", "Chuvashes": "Chuvash", "Livs": "Liv",
             "Other ethnicities, including not selected and not indicated ethnicity":
                 "Other or not stated"}


def url(table: str, lang: str = "en") -> str:
    return f"{EN if lang == 'en' else LV}/{TABLES[table]}"


def meta(table: str, lang: str = "en") -> dict[str, dict[str, Any]]:
    return {v["code"]: v for v in request_json(url(table, lang), pause=0.5)["variables"]}


def query(table: str, pins: dict[str, Any]) -> list[tuple[dict[str, tuple[str, str]], float]]:
    return unstack(request_json(url(table), {"query": [
        {"code": k, "selection": ({"filter": "all", "values": ["*"]} if v == "*"
                                   else {"filter": "item", "values": list(v)})}
        for k, v in pins.items()], "response": {"format": "json-stat2"}}, pause=0.5))


def municipality_of(code: str) -> str:
    return code if code in STATE_CITIES else code[:6] + "000"


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    log("latvia: CSB IRD041, IRD031, IRE031, IRD081 and RIG040")

    # --- admin1: municipalities by single year of age.
    m41 = meta("IRD041")
    year = int(m41["TIME"]["values"][-1])
    areas = [c for c in m41["AREA"]["values"] if len(c) == 9]
    municipalities = [c for c in areas if c.endswith("000")]
    merged = [c for c in areas if c == "LV0038001"]      # Madona since July 2025
    singles = [a for a in m41["AGE"]["values"] if re.fullmatch(r"Y\d+", a)]
    opens = [a for a in m41["AGE"]["values"] if re.fullmatch(r"Y_GE\d+", a)]
    top = max(int(a[1:]) for a in singles)
    open_class = next(a for a in opens if int(a[4:]) == top + 1)
    people: dict[tuple[str, int], AgeSex] = defaultdict(AgeSex)
    totals: dict[tuple[str, int, str], float] = {}
    for when in (year, year - 1):
        rows = query("IRD041", {"AREA": municipalities + merged + ["LV"], "AGE": singles + [open_class,
                                "TOTAL"], "SEX": ["M", "F", "T"], "ContentsCode": ["IRD041"],
                                "TIME": [str(when)]})
        for key, value in rows:
            code, age, sex = key["AREA"][0], key["AGE"][0], key["SEX"][0]
            if age == "TOTAL":
                totals[(code, when, sex)] = value
            elif sex in ("M", "F"):
                people[(code, when)].add(top + 1 if age == open_class else int(age[1:]),
                                         "m" if sex == "M" else "f", value)
    for (code, when), got in people.items():
        if abs(got.total - totals.get((code, when, "T"), -1)) > 0.5:
            raise SystemExit(f"IRD041 {code} {when}: single years make {got.total:,.0f} of "
                             f"{totals.get((code, when, 'T'))}")
    for when in (year, year - 1):
        present = [c for c in municipalities + merged if totals.get((c, when, "T"))]
        # CSB carries the merged Madona back into 2025 beside the two it was
        # made from; count one or the other.
        if "LV0038000" in present:
            present = [c for c in present if c not in merged]
        check_parts({c: totals[(c, when, "T")] for c in present}, totals[("LV", when, "T")],
                    f"IRD041 {when}: municipalities -> Latvia", 0)
    medians = {(key["AREA"][0], int(key["TIME"][0])): value for key, value in query(
        "IRD031", {"SEX": ["T"], "AREA": municipalities, "ContentsCode": ["IRD0311"],
                   "TIME": [str(year), str(year - 1)]})}
    lv41 = meta("IRD041", "lv")["AREA"]
    lv_names = dict(zip(lv41["values"], lv41["valueTexts"]))

    eth_rows = query("IRE031", {"AREA": municipalities, "ETHNICITY": "*",
                                "ContentsCode": ["IRE031"], "TIME": [str(year), str(year - 1)]})
    ethnicity: dict[tuple[str, int], dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for key, value in eth_rows:
        code, when, (cat, text) = key["AREA"][0], int(key["TIME"][0]), key["ETHNICITY"]
        ethnicity[(code, when)]["__total__" if cat == "TOTAL" else ETHNICITY.get(text, text)] += value

    def eth_block(counts: dict[str, float], when: int, table: str, experimental: bool = False):
        counts = dict(counts)
        total = counts.pop("__total__", 0.0)
        if not total or abs(sum(counts.values()) - total) > 0.5:
            return {}
        return {
            "ethnicity": shares(counts, total=total),
            "ethnicity_year": when,
            "ethnicity_note": (
                f"Ethnicity as recorded in the population register at the beginning of {when} "
                f"(CSB, {table}{', experimental statistics' if experimental else ''}). 'Other or "
                "not stated' is CSB's own residual: other ethnicities together with people who "
                "selected none or did not indicate one."),
            "_source": {"field": "ethnicity", "name": f"{SOURCE}, {table}",
                        "url": PAGE.format(folder="IRE", table=table), "year": when},
        }

    records = []
    admin1 = {fold(u["name"]): u for u in load_units("LVA", "admin1")}
    for code in municipalities:
        when = year - 1 if code in PRE_MERGER else year
        name = re.sub(r"\s*\((?:no|līdz) [\d.]+\)\s*$", "", lv_names.get(code, code)).strip()
        shape = admin1.get(fold(name)) or admin1.get(fold(name) + "s")
        if shape is None:
            log(f"  no polygon for municipality {code} {name}")
            continue
        ages = people[(code, when)]
        fields = ages.fields(year=when, source=f"{SOURCE}, IRD041",
                             url=PAGE.format(folder="IRD", table="IRD041"),
                             date=f"the beginning of {when}", extra_note=(
                                 " Madona and Varakļāni merged on 1 July 2025 and are drawn "
                                 "apart, so both are read before the merger."
                                 if code in PRE_MERGER else ""))
        if (code, when) in medians:
            fields["median_age"] = measure(medians[(code, when)], unit="years", year=when,
                                           source=f"{SOURCE}, IRD031")
            fields["median_age_note"] = (f"The median age at the beginning of {when} as CSB "
                                         "publishes it for the municipality (IRD031).")
            fields["sources"].append({"field": "median age", "name": f"{SOURCE}, IRD031",
                                      "url": PAGE.format(folder="IRD", table="IRD031"),
                                      "year": when})
        block = eth_block(ethnicity[(code, when)], when, "IRE031")
        if block:
            fields["sources"].append(block.pop("_source"))
            fields.update(block)
        records.append(record(
            f"LVA-CSB-{code}", name, level="admin1", parent="LVA", country="LVA",
            codes={"atvk": code}, match_by="shape_id", shape_id=shape["id"],
            aliases=[shape["name"]] if shape["name"] != name else [], **fields))
    log(f"  admin1: {len(records)} municipalities written")

    # --- admin2: parishes and towns by five-year group.
    m81 = meta("IRD081")
    lv81 = meta("IRD081", "lv")
    names81 = dict(zip(lv81["AREA"]["values"], lv81["AREA"]["valueTexts"]))
    units = [c for c in m81["AREA"]["values"] if re.fullmatch(r"LV00\d{5}", c)
             and (not c.endswith("000") or c in STATE_CITIES)]
    bands = [a for a in m81["AgeGroup"]["values"]
             if (re.fullmatch(r"Y(\d+)-(\d+)", a) and
                 int(a[1:].split("-")[1]) - int(a[1:].split("-")[0]) == 4) or a == "Y_GE85"]
    groups: dict[str, dict[str, dict[str, float]]] = defaultdict(lambda: defaultdict(dict))
    for chunk in (units[i:i + 150] for i in range(0, len(units), 150)):
        for key, value in query("IRD081", {"SEX": ["T", "M", "F"], "AgeGroup": bands + ["TOTAL"],
                                           "AREA": chunk, "ContentsCode": ["IRD081"],
                                           "TIME": [str(year)]}):
            groups[key["AREA"][0]][key["SEX"][0]][key["AgeGroup"][0]] = value
    for code, by_sex in groups.items():
        for sex, cells in by_sex.items():
            parts = sum(v for g, v in cells.items() if g != "TOTAL")
            if abs(parts - cells.get("TOTAL", 0)) > 0.5:
                raise SystemExit(f"IRD081 {code} {sex}: groups make {parts:,.0f} of "
                                 f"{cells.get('TOTAL', 0):,.0f}")
        if abs(by_sex["M"].get("TOTAL", 0) + by_sex["F"].get("TOTAL", 0)
               - by_sex["T"].get("TOTAL", 0)) > 0.5:
            raise SystemExit(f"IRD081 {code}: males and females do not make the total")
    for muni in municipalities:
        if muni in PRE_MERGER or not totals.get((muni, year, "T")):
            continue
        inside = [c for c in units if municipality_of(c) == muni and c != muni]
        if muni in STATE_CITIES:
            inside = [muni]
        # Jēkabpils, Ogre and Valmiera are towns inside their novadi.
        check_parts({c: groups[c]["T"].get("TOTAL", 0) for c in inside},
                    totals[(muni, year, "T")], f"IRD081 {year}: units -> {lv_names[muni]}", 0)

    rig = query("RIG040", {"AllAreaLV": units, "ETHNICITY": "*", "ContentsCode": ["RIG040"],
                           "TIME": [str(year)]})
    unit_eth: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for key, value in rig:
        code, (cat, text) = key["AllAreaLV"][0], key["ETHNICITY"]
        unit_eth[code]["__total__" if cat == "TOTAL" else ETHNICITY.get(text, text)] += value

    # Drawn names: "Ainažu pag." for a parish, the town's name for a town.
    def drawn(shape: dict[str, Any]) -> str:
        return re.sub(r"\s+pag\.$", " pagasts", shape["name"]).strip()

    shapes = load_units("LVA", "admin2")
    drawn_names = {fold(drawn(s)) for s in shapes}
    rows = {}
    for code in units:
        name = re.sub(r"\s*\([^()]*\)\s*$", "", names81.get(code, code).lstrip(".")).strip()
        if code in REJOINED.values() and fold(name) not in drawn_names:
            continue                         # a town counted inside its parish below
        parent = lv_names.get(municipality_of(code), "")
        rows[code] = (name, re.sub(r"\s*\((?:no|līdz) [\d.]+\)\s*$", "", parent).strip())
    bound, _missing, _left, _pieces = bind_rows("LVA", "admin2", rows, shape_name=drawn)
    date = f"the beginning of {year}"
    for code, sid in sorted(bound.items()):
        parts = [code]
        if code in REJOINED and REJOINED[code] not in rows:
            parts.append(REJOINED[code])
        cells: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        for part in parts:
            for sex, row in groups[part].items():
                for g, v in row.items():
                    cells[sex][g] += v
        total = cells["T"]["TOTAL"]
        men, women = cells["M"]["TOTAL"], cells["F"]["TOTAL"]
        bands_ = sorted((int(g[1:].split("-")[0]) if g != "Y_GE85" else 85,
                         int(g[1:].split("-")[1]) if g != "Y_GE85" else None, v)
                        for g, v in cells["T"].items() if g != "TOTAL")
        joined = (f" Counted with the town of {names81[REJOINED[code]].lstrip('.').strip()}, "
                  "which CSB separated from the parish after the map's boundaries were drawn."
                  if len(parts) > 1 else "")
        fields: dict[str, Any] = {
            "population": measure(int(round(total)), year=year, source=f"{SOURCE}, IRD081"),
            "population_note": f"Resident population at {date}.{joined}",
            "median_age": measure(grouped_median(bands_), unit="years", year=year,
                                  source=f"{SOURCE}, IRD081"),
            "median_age_note": (
                "Interpolated within the five-year age group that holds the middle person; CSB "
                "publishes the population of parishes and towns by five-year group, and nothing "
                f"finer.{joined}"),
            "sex_ratio": measure(sex_ratio(men, women), unit=SEX_RATIO_UNIT, year=year,
                                 source=f"{SOURCE}, IRD081"),
            "sex_ratio_note": (f"Males per 100 females among residents at {date} "
                               f"({int(men):,} males, {int(women):,} females)."),
            "sources": [{"field": "population/median age/sex ratio",
                         "name": f"{SOURCE}, IRD081",
                         "url": PAGE.format(folder="IRD", table="IRD081"), "year": year}],
        }
        counts: dict[str, float] = defaultdict(float)
        for part in parts:
            for k, v in unit_eth.get(part, {}).items():
                counts[k] += v
        block = eth_block(counts, year, "RIG040", experimental=True)
        if block:
            fields["sources"].append(block.pop("_source"))
            fields.update(block)
        records.append(record(
            f"LVA-CSB-{code}", rows[code][0], level="admin2", parent="LVA", country="LVA",
            parent_name=rows[code][1], codes={"atvk": code}, match_by="shape_id",
            shape_id=sid, **fields))
    labels = {g["group"] for r in records if isinstance(r.get("ethnicity"), list)
              for g in r["ethnicity"]}
    log(f"  ethnicity labels the group tree cannot place: {unplaced('ethnicity', labels)}")
    write_json(OUT, records)
    log(f"  wrote {OUT.name}: {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
