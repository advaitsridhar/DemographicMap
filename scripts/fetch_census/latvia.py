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
latest year) for the ethnicity, except for the ten state cities, for which
RIG040 gives no composition that makes the city's total: those take IRE031,
the register's count for the same territory. A unit whose ethnicities do not make its total gets none,
and its gap says so. Three parishes lost their centre to a new town
after the map's boundaries were drawn -- CSB gave each a new code when it did
(Ādažu 401, Ķekavas 421, Mārupes 411) -- and the map draws the parish whole,
without the town: the town and the parish are added together for it, and only
while the town has no polygon of its own.

**Language** was last asked in the 2011 census (the 2021 census was compiled
from registers, and none records language). CSB tabulates it (TSG11-07) by the
110 counties and 9 cities of 2009-2021, and lists the towns and parishes each
was made of (TSG11-01). A county is placed in the drawn municipality that
holds its towns and parishes, found by name, and a municipality is the sum of
the counties placed in it; a drawn town or parish that was a county on its
own (several small counties were one parish) or a city takes that county's or city's own figure.
Nothing is shared out to the parts of a county.

Religion is not asked by Latvia's census (existing policy).

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

from ._shared import NOT_AVAILABLE, PROCESSED, gap, log, measure, record, shares, write_json
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
# The three state cities the reform left inside a novads (Jēkabpils, Ogre,
# Valmiera): towns on the admin2 layer, and rows of their own in CSB's
# municipal tables, IRE031 among them.
CITY_TOWNS = ("LV0031010", "LV0040010", "LV0054010")
# Madona before its merger with Varakļāni, and Varakļāni: CSB's own codes for
# the two municipalities the map draws, which it lists until 2025.
PRE_MERGER = ("LV0038000", "LV0055000")
# The parishes whose centre became a town after the map's boundaries: the town
# (not drawn) and the parish (recoded) make the drawn parish.
REJOINED = {"LV0023401": "LV0023200", "LV0034421": "LV0034220", "LV0039411": "LV0039200"}

ETHNICITY = {"Latvians": "Latvian", "Russians": "Russian", "Belarusians": "Belarusian",
             "Ukrainians": "Ukrainian", "Poles": "Polish", "Lithuanians": "Lithuanian",
             "Jews": "Jewish", "Roma": "Romani", "Germans": "German", "Estonians": "Estonian",
             "Tatars": "Tatar", "Armenians": "Armenian", "Azerbaijanis": "Azerbaijani",
             "Moldavians": "Moldovan", "Indians": "Indian", "Georgians": "Georgian",
             "Uzbeks": "Uzbek", "Chuvashes": "Chuvash", "Livs": "Liv",
             "Other ethnicities, including not selected and not indicated ethnicity":
                 "Other or not stated"}


def ethnic_label(text: str) -> str:
    """CSB's label for an ethnicity, in the map's words. RIG040 words its
    residual as "Other ethnicities excluding Latvians, Russians, ...", which
    names peoples it does not count, so every residual is matched by its
    first words."""
    if text.startswith("Other ethnicities"):
        return "Other or not stated"
    return ETHNICITY.get(text, text)


def url(table: str, lang: str = "en") -> str:
    return f"{EN if lang == 'en' else LV}/{TABLES[table]}"


def meta(table: str, lang: str = "en") -> dict[str, dict[str, Any]]:
    return {v["code"]: v for v in request_json(url(table, lang), pause=0.5)["variables"]}


def query(table: str, pins: dict[str, Any]) -> list[tuple[dict[str, tuple[str, str]], float]]:
    return unstack(request_json(url(table), {"query": [
        {"code": k, "selection": ({"filter": "all", "values": ["*"]} if v == "*"
                                   else {"filter": "item", "values": list(v)})}
        for k, v in pins.items()], "response": {"format": "json-stat2"}}, pause=0.5))


# The 2011 census, the last to ask the language mostly spoken at home, by the
# 110 counties (novadi) and 9 cities of 2009-2021 (TSG11-07), and the towns
# and parishes each of those was made of (TSG11-01).
CENSUS = "https://data.stat.gov.lv/api/v1/{lang}/OSP_OD/tautassk/{path}"
CENSUS_LANG = "taut/tsk2011/TSG11-07.px"
CENSUS_UNITS = "demogr/tsk2011/TSG11-01.px"
CENSUS_PAGE = ("https://data.stat.gov.lv/pxweb/en/OSP_OD/OSP_OD__tautassk__taut__tsk2011/"
               "TSG11-07.px/")
# The nine cities of 2009-2021 (TSG11-01's codes) -> the drawn unit each is
# today: seven state cities, and Jēkabpils and Valmiera, towns inside their
# novadi since 2021. Ogre was a town of Ogre county in 2011.
OLD_CITIES = {"LV0010000": "LV0001000", "LV0050000": "LV0002000", "LV0090000": "LV0003000",
              "LV0110000": "LV0031010", "LV0130000": "LV0004000", "LV0170000": "LV0005000",
              "LV0210000": "LV0006000", "LV0250000": "LV0054010", "LV0270000": "LV0007000"}
TERRITORY = "Teritoriālā vienība"
HOME_LANGUAGE = "Mājās pārsvarā lietotā valoda"
LANGUAGES = {"LAV": "Latvian", "RUS": "Russian", "BEL": "Belarusian", "UKR": "Ukrainian",
             "POL": "Polish", "LIT": "Lithuanian", "OTH": "Other language"}


def census_units(values: list[str], texts: list[str]) -> dict[str, list[str]]:
    """TSG11-01's territory list -> {county or city code: the names of its parts}.

    The list runs region, then each county or city with its towns and parishes
    beneath it, marked by leading dots. A city with nothing beneath it is its
    own one part.
    """
    parts: dict[str, list[str]] = {}
    current = None
    for code, text in zip(values, texts):
        if not re.fullmatch(r"LV\d{7}", code):
            current = None
            continue
        if text.lstrip().startswith("."):
            if current is None:
                raise SystemExit(f"TSG11-01: {code} {text!r} stands under no county or city")
            parts[current].append(text.strip().lstrip(".").strip())
        else:
            current = code
            parts[code] = []
    return {code: names or [dict(zip(values, texts))[code].strip()]
            for code, names in parts.items()}


def place_census_units(old: dict[str, list[str]], new: dict[str, tuple[str, str]],
                       ) -> tuple[dict[str, str], dict[str, str]]:
    """Each 2011 county or city -> the drawn municipality holding its parts, and
    each 2011 unit made of one part -> the drawn town or parish that part is.

    ``new`` is {drawn unit code: (its name, its municipality's shape id)}. A
    part whose name is borne by units in more than one municipality (there are
    two Pilskalne parishes) decides nothing; every part that does decide must
    name the same municipality, and at least half of a unit's parts must be
    found, or the run stops.
    """
    where: dict[str, set[str]] = defaultdict(set)
    code_of: dict[tuple[str, str], str] = {}
    for code, (name, admin1) in new.items():
        where[fold(name)].add(admin1)
        code_of[(fold(name), admin1)] = code
    def key(name: str) -> str:
        """The name folded; failing that, without "pilsēta" (city), or -- for a
        county TSG11-01 lists with nothing beneath it, a county of one parish
        (Skrīveru novads) -- as the parish of the same name."""
        name = name.strip()
        for form in (name, re.sub(r"\s+(?:republikas\s+)?(?:pilsēta|city)$", "", name),
                     re.sub(r"\s+novads$", " pagasts", name)):
            if where.get(fold(form)):
                return fold(form)
        return fold(name)

    placed: dict[str, str] = {}
    single: dict[str, str] = {}
    failed = []
    for unit, names in old.items():
        names = [key(n) for n in names]
        found = [where[n] for n in names if where.get(n)]
        decisive = {next(iter(s)) for s in found if len(s) == 1}
        if len(decisive) != 1 or 2 * len(found) < len(names):
            failed.append(f"{unit}: parts {names} point to {sorted(decisive)} "
                          f"({len(found)} of {len(names)} found)")
            continue
        placed[unit] = decisive.pop()
        if len(names) == 1 and (names[0], placed[unit]) in code_of:
            single[unit] = code_of[(names[0], placed[unit])]
    if failed:
        raise SystemExit(f"TSG11-01: {len(failed)} units of 2011 not placed: " + "; ".join(failed))
    return placed, single


def census_language(records: list[dict[str, Any]], bound: dict[str, str],
                    rows: dict[str, tuple[str, str]], shapes: list[dict[str, Any]]) -> None:
    """The 2011 census's home language, written in place on the municipalities
    (summed from the 2009-2021 units that make each) and on each drawn town or
    parish that was a 2009-2021 unit on its own."""
    parent = {s["id"]: s.get("parent") for s in shapes}
    new = {code: (rows[code][0], parent[sid]) for code, sid in bound.items()}
    meta_units = request_json(CENSUS.format(lang="lv", path=CENSUS_UNITS), pause=0.5)
    territory = next(v for v in meta_units["variables"] if v["code"] == TERRITORY)
    old = census_units(territory["values"], territory["valueTexts"])
    for city, code in OLD_CITIES.items():
        if city not in old or code not in new:
            raise SystemExit(f"TSG11-01: the city {city} or its drawn unit {code} is missing")
        old[city] = [new[code][0]]         # the city by its code, not its genitive name
    placed, single = place_census_units(old, new)
    body = request_json(CENSUS.format(lang="en", path=CENSUS_LANG), {"query": [
        {"code": TERRITORY, "selection": {"filter": "all", "values": ["*"]}},
        {"code": "Dzimums", "selection": {"filter": "item", "values": ["T"]}},
        {"code": HOME_LANGUAGE, "selection": {"filter": "all", "values": ["*"]}},
        {"code": "Skaits, īpatsvars", "selection": {"filter": "item", "values": ["NUMB"]}},
        {"code": "Vecums (pilni gadi)", "selection": {"filter": "item", "values": ["TOTAL"]}},
    ], "response": {"format": "json-stat2"}}, pause=0.5)
    cells: dict[str, dict[str, float]] = defaultdict(dict)
    for key, value in unstack(body):
        cells[key[TERRITORY][0]][key[HOME_LANGUAGE][0]] = value
    missing = sorted(set(old) - set(cells))
    if missing:
        raise SystemExit(f"TSG11-07: no language for the 2011 units {missing}")
    for unit in list(old) + ["LV"]:
        parts = sum(cells[unit].get(c, 0) for c in LANGUAGES)
        if abs(parts - cells[unit].get("TOTAL", -1)) > 0.5:
            raise SystemExit(f"TSG11-07 {unit}: languages make {parts:,.0f} of "
                             f"{cells[unit].get('TOTAL')}")
    check_parts({u: cells[u]["TOTAL"] for u in old}, cells["LV"]["TOTAL"],
                "TSG11-07 2011: counties and cities -> Latvia", 0)
    summed: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    made_of: dict[str, list[str]] = defaultdict(list)
    for unit, admin1 in placed.items():
        made_of[admin1].append(unit)
        for c, label in LANGUAGES.items():
            summed[admin1][label] += cells[unit][c]
    names = dict(zip(territory["values"], territory["valueTexts"]))
    date = "1 March 2011"
    what = (f"Language mostly spoken at home, as answered in the census of {date} (CSB, "
            "TSG11-07) -- the last census to ask it: the 2021 census was compiled from "
            "registers and published no language.")
    source = {"field": "language", "name": f"{SOURCE}, 2011 census, TSG11-07",
              "url": CENSUS_PAGE, "year": 2011}

    def write(rec: dict[str, Any], counts: dict[str, float], note: str) -> None:
        rec["language"] = shares(counts, total=sum(counts.values()))
        rec["language_year"] = 2011
        rec["language_note"] = f"{what} {note}".strip()
        rec["sources"].append(source)

    got = 0
    for rec in records:
        if rec["level"] == "admin1" and rec.get("shape_id") in summed:
            units = made_of[rec["shape_id"]]
            write(rec, summed[rec["shape_id"]],
                  f"Summed from the {len(units)} units of 2009-2021 that make the municipality: "
                  + ", ".join(sorted(names[u].strip() for u in units)) + "."
                  if len(units) > 1 else "")
            got += 1
    drawn1 = {r["shape_id"] for r in records if r["level"] == "admin1"}
    log(f"  TSG11-07: {len(old)} units of 2011 placed in {len(summed)} municipalities; "
        f"language written for {got}; municipalities with none: "
        f"{sorted(r['name'] for r in records if r['level'] == 'admin1' and r['shape_id'] not in summed)}")
    if not drawn1 <= set(summed):
        raise SystemExit("TSG11-07: a drawn municipality holds no 2011 unit")
    by_code = {r["codes"]["atvk"]: r for r in records if r["level"] == "admin2"}
    for unit, code in single.items():
        write(by_code[code], {label: cells[unit][c] for c, label in LANGUAGES.items()},
              f"In 2011 this was a unit of its own ({names[unit].strip()}), so the census's "
              "figure is for exactly this territory.")
    log(f"  TSG11-07: language written for {len(single)} towns and parishes that were a unit "
        "of 2009-2021 on their own")


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

    eth_rows = query("IRE031", {"AREA": municipalities + list(CITY_TOWNS), "ETHNICITY": "*",
                                "ContentsCode": ["IRE031"], "TIME": [str(year), str(year - 1)]})
    ethnicity: dict[tuple[str, int], dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for key, value in eth_rows:
        code, when, (cat, text) = key["AREA"][0], int(key["TIME"][0]), key["ETHNICITY"]
        ethnicity[(code, when)]["__total__" if cat == "TOTAL" else ethnic_label(text)] += value

    def eth_block(counts: dict[str, float], when: int, table: str, where: str,
                  experimental: bool = False) -> dict[str, Any]:
        """The ethnicity fields, or a note saying why there are none."""
        counts = dict(counts)
        total = counts.pop("__total__", 0.0)
        if not total or abs(sum(counts.values()) - total) > 0.5:
            why = (f"CSB's {table} has no figure for this unit at the beginning of {when}"
                   if not total else
                   f"the ethnicities in CSB's {table} make {sum(counts.values()):,.0f} of the "
                   f"unit's {total:,.0f} residents at the beginning of {when}")
            log(f"  {table} {where}: {why}; ethnicity left out")
            return {"ethnicity": gap(NOT_AVAILABLE, f"Not given: {why}.")}
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
        block = eth_block(ethnicity[(code, when)], when, "IRE031", name)
        if "_source" in block:
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
             and (not c.endswith("000") or c in STATE_CITIES) and c != "LV0038001"]
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
        unit_eth[code]["__total__" if cat == "TOTAL" else ethnic_label(text)] += value

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
        if code in STATE_CITIES or code in CITY_TOWNS:
            # A state city is one territory at both levels, and IRE031 is the
            # register's count for it; RIG040 gives none of the ten a
            # composition that makes its total.
            block = eth_block(ethnicity[(code, year)], year, "IRE031", rows[code][0])
        else:
            for part in parts:
                for k, v in unit_eth.get(part, {}).items():
                    counts[k] += v
            block = eth_block(counts, year, "RIG040", rows[code][0], experimental=True)
        if "_source" in block:
            fields["sources"].append(block.pop("_source"))
        fields.update(block)
        records.append(record(
            f"LVA-CSB-{code}", rows[code][0], level="admin2", parent="LVA", country="LVA",
            parent_name=rows[code][1], codes={"atvk": code}, match_by="shape_id",
            shape_id=sid, **fields))
    census_language(records, bound, rows, shapes)
    labels = {g["group"] for r in records if isinstance(r.get("ethnicity"), list)
              for g in r["ethnicity"]}
    log(f"  ethnicity labels the group tree cannot place: {unplaced('ethnicity', labels)}")
    write_json(OUT, records)
    log(f"  wrote {OUT.name}: {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
