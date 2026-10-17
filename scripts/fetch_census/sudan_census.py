#!/usr/bin/env python3
"""Sudan -- the 2008 census by state and locality: sex ratio, and median age.

Sudan's last census, the Fifth Population and Housing Census of 21 April 2008,
is what OCHA's population tables for 2025 are projected from. The census's own
figures are in the US Census Bureau's subnational tables for HDX
(``sudan-subnational-boundaries-and-tabular-data``), in two sheets:

* ``Population_RetabGeog``: the census's priority results -- everyone by sex
  -- retabulated by the Bureau to the 18 states, 173 localities and 408
  administrative units of 2020, from the census's own counts of the units
  below them;
* ``Population_CensusGeog``: Table P01, everyone by five-year age group and
  sex, for the 15 northern states as they stood in 2008.

**What is written**, as the census's own figures, which stand in front of the
2025 projections: men per 1,000 women for every state and every locality the
map draws that the retabulation names, and the median age for every state
whose ground has not changed since 2008 -- a state whose 2008 count in Table
P01 is the same, to the person, as the retabulation's count of the state as
drawn in 2020. The states made since (Central and East Darfur, West Kordofan)
and those they were taken from have no census median, and say nothing here.
No head count is written: the projections are of later years.

**Checks before anything is written.** Every row's men and women make its
total and its age groups make it too; the localities of each state make the
state, and the states the country. Localities bind to the map's within their
state by name, then by the closest spelling where each is the other's best;
every pairing that is not exact is logged.

**Claimed ground.** The Abyei Area, which Sudan and South Sudan both claim,
and Hala'ib, whose triangle north of 22°N Egypt and Sudan both claim, are
never written.

Usage:
    python -m scripts.fetch_census.sudan_census
"""

from __future__ import annotations

import argparse
import io
import json
import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any

from . import uscb
from ._shared import PROCESSED, http_get, log, measure, record, write_json

DATASET = "sudan-subnational-boundaries-and-tabular-data"
YEAR = 2008
OUT = "sudan_census.json"
SITE = PROCESSED.parent.parent / "site" / "data"
RETAB_SOURCE = ("Central Bureau of Statistics (Sudan), Fifth Population and Housing Census "
                "2008, priority results by sex, retabulated to the states and localities of "
                "2020 by the US Census Bureau for HDX")
AGE_SOURCE = ("Central Bureau of Statistics (Sudan), Fifth Population and Housing Census 2008, "
              "Table P01: population by five-year age group and sex, as the US Census Bureau "
              "tabulates it for HDX")
LICENCE = "Creative Commons Attribution International (CC BY), published via HDX"
# The retabulation's locality (folded) -> the map's label, where neither the
# names nor the closest spelling join them. Filled from the run's log.
LOCALITIES: dict[str, str] = {}
CLAIMED = ("abyei", "halaib", "halayeb")
# The most of a state's people Table P01 may leave without a stated age
# before the table is taken to be misread rather than incomplete.
UNSTATED_SHARE = 0.05
SPELLING = 0.72
GROUP = re.compile(r"^([BMF])(\d{2})(\d{2})$")
OPEN = re.compile(r"^([BMF])(\d{2})PL$")


def fold(text: Any) -> str:
    stripped = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(c for c in stripped.lower() if c.isalpha() and not unicodedata.combining(c))


def number(value: Any) -> int | None:
    got = uscb.number(value)
    return None if got is None else int(round(got))


def grouped_median(groups: list[tuple[int, int | None, int]]) -> float | None:
    base = sum(n for _, _, n in groups)
    half, before = base / 2, 0
    for low, high, people in groups:
        if before + people >= half:
            if high is None or people <= 0:
                return None
            return round(low + (half - before) / people * (high - low + 1), 1)
        before += people
    return None


def find(aliases: list[str], names: list[str], alias: str) -> int:
    """The one column whose alias is exactly this."""
    hits = [i for i, a in enumerate(aliases) if a.strip().lower() == alias.lower() and names[i]]
    if len(hits) != 1:
        raise SystemExit(f"sudan_census: {len(hits)} columns are aliased {alias!r}")
    return hits[0]


def read_retab(rows: list[list[Any]]) -> dict[str, Any]:
    names, aliases = uscb.columns(rows)
    at = {n: i for i, n in enumerate(names) if n}
    men_col = find(aliases, names, "Male Population, institutional and non-institutional population")
    women_col = find(aliases, names,
                     "Female Population, institutional and non-institutional population")
    total_col = find(aliases, names,
                     "Total Population, institutional and non-institutional population")
    out: dict[str, Any] = {"national": None, "states": {}, "localities": []}
    for row in rows[2:]:
        level = number(row[at["ADM_LEVEL"]])
        if level not in (0, 1, 2):
            continue
        name = str(row[at["AREA_NAME"]] or "").strip()
        men, women, total = number(row[men_col]), number(row[women_col]), number(row[total_col])
        if None in (men, women, total) or men + women != total:
            raise SystemExit(f"sudan_census: {name}: men {men}, women {women}, total {total}")
        unit = {"name": name, "men": men, "women": women, "total": total,
                "state": str(row[at["ADM1_NAME"]] or "").strip(),
                "code": str(row[at["GEO_MATCH"]] or name).strip()}
        if level == 0:
            out["national"] = unit
        elif level == 1:
            out["states"][fold(name)] = unit
        else:
            out["localities"].append(unit)
    for key, state in out["states"].items():
        made = sum(u["total"] for u in out["localities"] if fold(u["state"]) == key)
        if made != state["total"]:
            raise SystemExit(f"sudan_census: {state['name']}'s localities make {made:,}, not "
                             f"{state['total']:,}")
    if sum(s["total"] for s in out["states"].values()) != out["national"]["total"]:
        raise SystemExit("sudan_census: the states do not make the national total")
    return out


def read_ages(rows: list[list[Any]]) -> dict[str, dict[str, Any]]:
    """The 2008 states of Table P01: {folded name: {"total", "men", "women", "groups"}}."""
    names, _ = uscb.columns(rows)
    at = {n: i for i, n in enumerate(names) if n}
    cols: dict[str, list[tuple[int, int | None, int]]] = {"B": [], "M": [], "F": []}
    for i, name in enumerate(names):
        if m := GROUP.match(name):
            cols[m.group(1)].append((int(m.group(2)), int(m.group(3)), i))
        elif m := OPEN.match(name):
            cols[m.group(1)].append((int(m.group(2)), None, i))
    for sex, groups in cols.items():
        groups.sort(key=lambda g: g[0])
        edge = 0
        for low, high, _ in groups:
            if low != edge:
                raise SystemExit(f"sudan_census: P01's {sex} groups break at {low}")
            edge = high + 1 if high is not None else None
        if not groups or groups[-1][1] is not None:
            raise SystemExit(f"sudan_census: P01 has no open-ended {sex} group")
    out: dict[str, dict[str, Any]] = {}
    for row in rows[2:]:
        if number(row[at["ADM_LEVEL"]]) != 1:
            continue
        name = str(row[at["AREA_NAME"]] or "").strip()
        total, men, women = (number(row[at[k]]) for k in ("BTOTL", "MTOTL", "FTOTL"))
        groups = [(lo, hi, number(row[i]) or 0) for lo, hi, i in cols["B"]]
        if None in (total, men, women) or men + women != total:
            raise SystemExit(f"sudan_census: P01 {name}: men {men}, women {women}, "
                             f"total {total}")
        aged = sum(n for _, _, n in groups)
        by_sex = [sum(number(row[i]) or 0 for _, _, i in cols[s]) for s in "MF"]
        # People whose age was not stated are in the total and in no group:
        # they are left out of the median, and must be few.
        unstated = total - aged
        if unstated < 0 or unstated > UNSTATED_SHARE * total:
            raise SystemExit(f"sudan_census: P01 {name}: its age groups make {aged:,} of "
                             f"{total:,} (men {by_sex[0]:,} of {men:,}, women {by_sex[1]:,} "
                             f"of {women:,})")
        if unstated:
            log(f"  P01 {name}: {unstated:,} of {total:,} of no stated age (men "
                f"{men - by_sex[0]:,}, women {women - by_sex[1]:,})")
        out[fold(name)] = {"name": name, "total": total, "men": men, "women": women,
                           "groups": groups, "unstated": unstated}
    return out


def pair(units: list[dict[str, Any]], shapes: list[dict[str, Any]], report: list[str]
         ) -> dict[str, dict[str, Any]]:
    """Locality code -> polygon, within one state."""
    bound: dict[str, dict[str, Any]] = {}
    free = {s["id"]: s for s in shapes}
    left = []
    for unit in units:
        wanted = fold(LOCALITIES.get(fold(unit["name"]), unit["name"]))
        hits = [s for s in free.values() if fold(s["name"]) == wanted]
        if len(hits) == 1:
            bound[unit["code"]] = hits[0]
            del free[hits[0]["id"]]
        else:
            left.append(unit)

    def ratio(unit: dict[str, Any], shape: dict[str, Any]) -> float:
        return SequenceMatcher(None, fold(unit["name"]), fold(shape["name"])).ratio()
    for unit in left:
        if not free:
            report.append(f"    {unit['name']} ({unit['total']:,}): no polygon left")
            continue
        best = max(free.values(), key=lambda s: ratio(unit, s))
        back = max(left, key=lambda u: ratio(u, best))
        if ratio(unit, best) >= SPELLING and back is unit:
            report.append(f"    {unit['name']} -> {best['name']!r} by spelling "
                          f"({ratio(unit, best):.2f})")
            bound[unit["code"]] = best
            del free[best["id"]]
        else:
            report.append(f"    {unit['name']} ({unit['total']:,}): no polygon (closest "
                          f"{best['name']!r}, {ratio(unit, best):.2f})")
    for shape in free.values():
        report.append(f"    polygon {shape['name']!r}: no locality")
    return bound


def build(retab: dict[str, Any], ages: dict[str, dict[str, Any]],
          admin1: list[dict[str, Any]], admin2: list[dict[str, Any]]
          ) -> tuple[list[dict[str, Any]], list[str]]:
    report: list[str] = []
    records: list[dict[str, Any]] = []
    states = {fold(s["name"]): s for s in admin1}
    retab_src = {"name": RETAB_SOURCE, "url": uscb.dataset_url(DATASET), "year": YEAR,
                 "license": LICENCE}
    age_src = {"name": AGE_SOURCE, "url": uscb.dataset_url(DATASET), "year": YEAR,
               "license": LICENCE}
    for key, unit in sorted(retab["states"].items()):
        shape = states.get(key)
        if shape is None:
            report.append(f"  state {unit['name']}: no polygon")
            continue
        fields: dict[str, Any] = {
            "sex_ratio": measure(round(1000 * unit["men"] / unit["women"]),
                                 unit="males_per_1000_females", year=YEAR, source=RETAB_SOURCE),
            "sex_ratio_note": (f"Men per 1,000 women at the 2008 census in {unit['name'].title()} "
                               f"as drawn in 2020: {unit['men']:,} men and {unit['women']:,} "
                               f"women."),
            "sources": [{**retab_src, "field": "sex_ratio"}]}
        p01 = ages.get(key)
        if p01 and p01["total"] == unit["total"]:
            median = grouped_median(p01["groups"])
            fields["median_age"] = measure(median, unit="years", year=YEAR, source=AGE_SOURCE)
            unstated = (f" The {p01['unstated']:,} people whose age was not stated are left "
                        "out of it." if p01.get("unstated") else "")
            fields["median_age_note"] = (
                "Interpolated within the five-year age group that holds the middle person, "
                f"from the 2008 census's count of everyone in the state by five-year age group "
                f"({p01['total']:,} people, the state then as now).{unstated}")
            fields["sources"].append({**age_src, "field": "median_age"})
            report.append(f"  state {unit['name']}: unchanged since 2008 "
                          f"({unit['total']:,}); median {median}")
        else:
            report.append(f"  state {unit['name']}: {unit['total']:,} as drawn in 2020, "
                          f"{p01['total'] if p01 else 'no'} in P01; no census median")
        records.append(record(f"SDN-2008-{key}", shape["name"], level="admin1", parent="SDN",
                              country="SDN", match_by="shape_id", shape_id=shape["id"],
                              **fields))
        shapes = [s for s in admin2 if s["parent"] == shape["id"]]
        units = [u for u in retab["localities"] if fold(u["state"]) == key
                 and not any(c in fold(u["name"]) for c in CLAIMED)]
        claimed = [u["name"] for u in retab["localities"] if fold(u["state"]) == key
                   and any(c in fold(u["name"]) for c in CLAIMED)]
        if claimed:
            report.append(f"  {unit['name']}: not written, on claimed ground: {claimed}")
        shapes = [s for s in shapes if not any(c in fold(s["name"]) for c in CLAIMED)]
        report.append(f"  {unit['name']}: {len(units)} localities, {len(shapes)} polygons")
        for code, polygon in pair(units, shapes, report).items():
            loc = next(u for u in units if u["code"] == code)
            records.append(record(
                f"SDN-2008-{code}", polygon["name"], level="admin2", parent="SDN",
                country="SDN", match_by="shape_id", shape_id=polygon["id"],
                sex_ratio=measure(round(1000 * loc["men"] / loc["women"]),
                                  unit="males_per_1000_females", year=YEAR, source=RETAB_SOURCE),
                sex_ratio_note=(f"Men per 1,000 women at the 2008 census in the locality of "
                                f"{loc['name'].title()} as drawn in 2020: {loc['men']:,} men "
                                f"and {loc['women']:,} women."),
                codes={"uscb": code},
                sources=[{**retab_src, "field": "sex_ratio"}]))
    return records, report


def main() -> int:
    argparse.ArgumentParser(description=__doc__,
                            formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    import openpyxl                                 # noqa: PLC0415
    blob = http_get(uscb.workbook_url(DATASET), binary=True, cache=False, timeout=180)
    book = openpyxl.load_workbook(io.BytesIO(blob), read_only=True, data_only=True)
    retab = read_retab(uscb.sheet_rows(book, "Population_RetabGeog"))
    ages = read_ages(uscb.sheet_rows(book, "Population_CensusGeog"))
    log(f"  retabulation: {len(retab['states'])} states, {len(retab['localities'])} localities, "
        f"{retab['national']['total']:,} people; P01: {len(ages)} states of 2008")
    admin1 = json.loads((SITE / "admin1" / "SDN.units.json").read_text())
    admin2 = json.loads((SITE / "admin2" / "SDN.units.json").read_text())
    records, report = build(retab, ages, admin1, admin2)
    for line in report:
        log(line)
    log(f"  {sum(r['level'] == 'admin1' for r in records)} states and "
        f"{sum(r['level'] == 'admin2' for r in records)} of {len(admin2)} localities bound")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
