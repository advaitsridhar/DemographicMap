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
2025 projections:

* men per 1,000 women for every state;
* the median age for every state whose ground has not changed since 2008.
  Table P01 and the retabulation count the same states 1-2% apart (P01 has
  Khartoum's 5,181,186 people of the 5,274,321 the census counted), and the
  states taken apart since -- West and South Darfur in 2012 for Central and
  East Darfur, North and South Kordofan in 2013 for West Kordofan -- 30-70%
  apart: a state P01 counts within ``SAME_GROUND`` of the retabulation is the
  state then as now;
* men per 1,000 women for the localities of a state whose localities the
  retabulation and the map count alike, each bound by name, by a declared
  label (``LOCALITIES``) or by the closest spelling where each is the other's
  best. Where the map draws more localities than the retabulation names, some
  have been divided since and none is written.

No head count is written: the projections are of later years.

**Checks before anything is written.** Every row's men and women make its
total (to within two people of rounding) and its age groups make it too; the
localities of each state make the state, and the states the country. Every
pairing that is not exact is logged.

**Claimed ground.** The Abyei Area, which Sudan and South Sudan both claim,
and Hala'ib, whose triangle north of 22°N Egypt and Sudan both claim, are
never written: a state that holds one (West Kordofan, Red Sea) is written
without that locality's people, which its note says, and Red Sea, whose ages
Table P01 gives only with Hala'ib's, has no median.

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
# names nor the closest spelling join them; only in states whose localities
# both count alike. "Reifi" is "rural", "Madeinat" "town of", "Sharg" "east".
LOCALITIES: dict[str, str] = {
    # Khartoum
    "jabalawlya": "Jebel Awlia", "khartoumnorth": "Bahri",
    # Kassala
    "aldaltanorth": "Reifi Shamal Ad Delta", "aromarural": "Reifi Aroma",
    "hamashkoreeb": "Reifi Hamashkureib", "kassala": "Madeinat Kassala",
    "kassalarural": "Reifi Kassla", "kassalawest": "Reifi Gharb Kassala",
    "khashmalqirbah": "Reifi Khashm Elgirba", "talkook": "Reifi Telkok",
    "wadalhulaywah": "Reifi Wad Elhilaiw",
    # Gedaref: the town, the centre, the two Gallabats, Qureisha; Gedaref
    # North, the Butana plain north of the town, is the one left of twelve.
    "gedaref": "Madeinat Al Gedaref", "gedarefcentral": "Wasat Al Gedaref",
    "qallabateast": "Galabat Ash-Shargiah", "qallabatwest": "Al Galabat Al Gharbyah - Kassab",
    "qurayshah": "Al Qureisha", "gedarefnorth": "Al Butanah",
    # Red Sea
    "derudeb": "Dordieb", "gebeit": "Jubayt Elma'aadin", "hillatagig": "Agig",
    # Northern: Golid's seat is at Agori, the one left of seven.
    "bergeig": "Al Burgaig", "dalqu": "Delgo", "marawi": "Merwoe", "wadihalfa": "Halfa",
    "agori": "Al Golid",
    # North Kordofan
    "barahwest": "Gharb Bara", "jabratelshiekh": "Gebrat Al Sheikh", "sawdiri": "Soudari",
    # East Darfur
    "eddaein": "Ad Du'ayn", "yaseen": "Yassin",
    # Sennar
    "sennarshareq": "Sharg Sennar",
}
CLAIMED = ("abyei", "halaib", "halayeb")
# How far apart Table P01 and the retabulation may count a state for its ground
# to be taken as unchanged since 2008 (they are 0.7-2.1% apart for the eleven
# states not divided since, 30-70% for the four that were).
SAME_GROUND = 0.03
# The most of a state's people Table P01 may leave without a stated age
# before the table is taken to be misread rather than incomplete.
UNSTATED_SHARE = 0.05
# How far a row's men and women may miss its total, and Table P01's count of
# a state the retabulation's, in people: the Bureau's cells are rounded one by
# one (P01 gives Khartoum 2,725,185 men and 2,456,002 women, 5,181,186 in all).
SLACK = 2
SPELLING = 0.72
GROUP = re.compile(r"^([BMF])(\d{2})(\d{2})$")
OPEN = re.compile(r"^([BMF])(\d{2})PL$")


def fold(text: Any) -> str:
    stripped = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(c for c in stripped.lower() if c.isalpha() and not unicodedata.combining(c))


def display(name: str) -> str:
    """The Bureau's capitals in title case, its transliteration marks kept."""
    words = []
    for w in str(name).lower().split():
        at = next((i for i, c in enumerate(w) if c.isalpha()), 0)
        words.append(w[:at] + w[at:at + 1].upper() + w[at + 1:])
    return " ".join(words)


def claim(name: str) -> str:
    """Where a claimed locality lies, for a visitor's note."""
    if "abyei" in fold(name):
        return "in the Abyei Area, which Sudan and South Sudan both claim"
    return ("which reaches onto the triangle north of the 22nd parallel that Sudan and Egypt "
            "both claim")


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
        if None in (men, women, total) or abs(men + women - total) > SLACK:
            raise SystemExit(f"sudan_census: {name}: men {men}, women {women}, total {total}")
        if men + women != total:
            log(f"  {name}: {men:,} men and {women:,} women against {total:,} (rounding)")
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
        if None in (total, men, women) or abs(men + women - total) > SLACK:
            raise SystemExit(f"sudan_census: P01 {name}: men {men}, women {women}, "
                             f"total {total}")
        if men + women != total:
            log(f"  P01 {name}: {men:,} men and {women:,} women against {total:,} (rounding)")
        aged = sum(n for _, _, n in groups)
        by_sex = [sum(number(row[i]) or 0 for _, _, i in cols[s]) for s in "MF"]
        # People whose age was not stated are in the total and in no group:
        # they are left out of the median, and must be few. A difference no
        # bigger than half a person a group is the rounding of the cells.
        unstated = total - aged
        if abs(unstated) <= len(groups) // 2:
            if unstated:
                log(f"  P01 {name}: its age groups make {aged:,} of {total:,} (rounding)")
            unstated = 0
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
        mine = [u for u in retab["localities"] if fold(u["state"]) == key]
        units = [u for u in mine if not any(c in fold(u["name"]) for c in CLAIMED)]
        claimed = [u for u in mine if u not in units]
        men = unit["men"] - sum(u["men"] for u in claimed)
        women = unit["women"] - sum(u["women"] for u in claimed)
        title = display(unit["name"])
        without = ""
        if claimed:
            without = " " + " ".join(
                f"It leaves out the locality of {display(u['name'])} ({u['total']:,} people), "
                f"{claim(u['name'])}." for u in claimed)
            report.append(f"  {unit['name']}: written without the claimed "
                          f"{[u['name'] for u in claimed]}")
        fields: dict[str, Any] = {
            "sex_ratio": measure(round(1000 * men / women),
                                 unit="males_per_1000_females", year=YEAR, source=RETAB_SOURCE),
            "sex_ratio_note": (f"Men per 1,000 women at the 2008 census in {title} as drawn in "
                               f"2020: {men:,} men and {women:,} women.{without}"),
            "sources": [{**retab_src, "field": "sex_ratio"}]}
        p01 = ages.get(key)
        if p01 and claimed:
            report.append(f"  state {unit['name']}: P01 counts it with {claimed[0]['name']}; "
                          f"no census median")
        elif p01 and abs(p01["total"] / unit["total"] - 1) <= SAME_GROUND:
            median = grouped_median(p01["groups"])
            fields["median_age"] = measure(median, unit="years", year=YEAR, source=AGE_SOURCE)
            unstated = (f" The {p01['unstated']:,} people whose age was not stated are left "
                        "out of it." if p01.get("unstated") else "")
            fields["median_age_note"] = (
                "Interpolated within the five-year age group that holds the middle person, "
                f"from the 2008 census's table of the state's people by five-year age group "
                f"({p01['total']:,} people of the {unit['total']:,} it counted; the state "
                f"then as now).{unstated}")
            fields["sources"].append({**age_src, "field": "median_age"})
            report.append(f"  state {unit['name']}: unchanged since 2008 "
                          f"({p01['total']:,} in P01 of {unit['total']:,}); median {median}")
        else:
            report.append(f"  state {unit['name']}: {unit['total']:,} as drawn in 2020, "
                          f"{p01['total'] if p01 else 'none'} in P01; no census median")
        records.append(record(f"SDN-2008-{key}", shape["name"], level="admin1", parent="SDN",
                              country="SDN", match_by="shape_id", shape_id=shape["id"],
                              **fields))
        shapes = [s for s in admin2 if s["parent"] == shape["id"]
                  and not any(c in fold(s["name"]) for c in CLAIMED)]
        if len(units) != len(shapes):
            report.append(f"  {unit['name']}: {len(units)} localities in 2008, {len(shapes)} "
                          f"drawn; divided since, none written")
            continue
        report.append(f"  {unit['name']}: {len(units)} localities, {len(shapes)} polygons")
        for code, polygon in pair(units, shapes, report).items():
            loc = next(u for u in units if u["code"] == code)
            records.append(record(
                f"SDN-2008-{code}", polygon["name"], level="admin2", parent="SDN",
                country="SDN", match_by="shape_id", shape_id=polygon["id"],
                sex_ratio=measure(round(1000 * loc["men"] / loc["women"]),
                                  unit="males_per_1000_females", year=YEAR, source=RETAB_SOURCE),
                sex_ratio_note=(f"Men per 1,000 women at the 2008 census in the locality of "
                                f"{display(loc['name'])} as drawn in 2020: {loc['men']:,} men "
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
